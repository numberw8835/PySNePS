# This file is part of PySNePS, a Python translation of SNePS 2.8; see
# CHANGES.md for the changes and COPYING for the License.
#
# The contents of this file are subject to the University at Buffalo Public
# License Version 1.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.cse.buffalo.edu/sneps/Downloads/ubpl.pdf.
#
# Software distributed under the License is distributed on an "AS IS" basis,
# WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
# the specific language governing rights and limitations under the License.
#
# The Original Code is SNePS 2.8.
#
# The Initial Developer of the Original Code is Research Foundation of State
# University of New York, on behalf of University at Buffalo.
#
# Portions created by the Initial Developer are Copyright (C) 2010 Research
# Foundation of State University of New York, on behalf of University at
# Buffalo. All Rights Reserved.
#
# Contributor(s): numberw8835 (the translation to Python, 2026).
"""SNePSLOG sessions (SNePS 2.8 ``snepslog``: the top level, the reader,
mode 3, tell/ask and the entrenchment orders).

SNePSLOG represents a predicate application ``P(a, b)`` in one of three
modes: mode 1 uses the relations ``r``, ``a1``, ``a2``...; mode 2 uses
relations derived from the predicate name; mode 3 uses case frames
declared with ``define-frame``.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

from ..core.network import SNePSError
from ..core.node import Node
from ..io.streams import InputStream, NullOutputStream, OutputStream
from ..core.printing import flat_text
from .generator import Generator, m_to_wff, printer
from .parser import Parser, SnepslogEnd

MODE3_FRAMES = [
    ("achieve", ["action", "object1"], "achieve [object1]"),
    ("ActPlan", [None, "act", "plan"], "to perform [act] do [plan]"),
    ("believe", ["action", "object1"], "believe [object1]"),
    ("disbelieve", ["action", "object1"], "disbelieve [object1]"),
    ("adopt", ["action", "object1"], "adopt policy [object1]"),
    ("unadopt", ["action", "object1"], "unadopt policy [object1]"),
    ("do-all", ["action", "object1"], "perform [object1]"),
    ("do-one", ["action", "object1"], "perform one of [object1]"),
    ("Effect", [None, "act", "effect"], "the effect of [act] is [effect]"),
    ("else", [None, "else"], "otherwise perform [else]"),
    ("GoalPlan", [None, "goal", "plan"], "in order to acheive [goal] do [plan]"),
    ("if", [None, "condition", "then"], "if [condition], then perform [then]"),
    ("ifdo", [None, "if", "do"], "if [if] do [do]"),
    ("Precondition", [None, "act", "precondition"],
     "[precondition] is required in order to perform [act]"),
    ("snif", ["action", "object1"], "snif: [object1]"),
    ("sniterate", ["action", "object1"], "sniterate: [object1]"),
    ("snsequence", ["action", "object1", "object2"], "perform [object1] then [object2]"),
    ("whendo", [None, "when", "do"], "when [when] do [do]"),
    ("wheneverdo", [None, "whenever", "do"], "whenever [whenever] do [do]"),
    ("withall", ["action", "vars", "suchthat", "do", "else"],
     "withall bindings of [vars] such that [suchthat] do [do] else [else]"),
    ("withsome", ["action", "vars", "suchthat", "do", "else"],
     "with one binding of [vars] such that [suchthat] do [do] else [else]"),
]

SNIP_ARC_DESCRIPTIONS = [
    (["forall", "ant", "cq"], "for all variables ([forall]), if one or more of {[ant]}, then [cq]"),
    (["forall", "&ant", "cq"], "for all variables ([forall]), if [&ant], then [cq]"),
    (["ant", "cq"], "if one or more of [ant], then [cq]"),
    (["&ant", "cq"], "if [&ant], then [cq]"),
    (["thresh", "&ant", "cq"], "if at least [thresh] of [&ant], then [cq]"),
    (["min", "max", "arg"], "at least of [min] and at most of [max] of [arg]"),
    (["thresh", "threshmax", "arg"], "either fewer than [thresh] or more than [threshmax] of [arg]"),
    (["emin", "emax", "etot", "pevb", "&ant", "cq"],
     "of the [etot] [pevb] that satisfy [&ant], at least [emin] and at most [emax] also satisfy [cq]"),
]


def _name(x: Any) -> Optional[str]:
    if x is None:
        return None
    return str(x)


class SnepslogMixin:
    """SNePSLOG, mixed into :class:`~sneps.Network`."""

    def _init_snepslog(self) -> None:
        self.snepslog_mode = 1
        self.complete_description = "normal"
        self.propargs: dict[str, list] = {}
        self.argsprop: dict[tuple, Any] = {}
        self.argsdesc: dict[tuple, Any] = {}
        self.associated_arcs: dict[str, list] = {}
        self.silent_mode3 = False
        self.trace_translation = False
        self.trace_parsing = False
        self.fluents: list = []
        self.snepslog_prompt = ":"
        self._sl_line: Optional[str] = None
        self._sl_index = 0
        self._sl_stream: Any = None
        self.generator = Generator(self)
        self.snepslog_parser = Parser(self)
        self.br_orders.update({"fluent": _fluent_order, "source": _source_order,
                               "explicit": _explicit_order})

    # ------------------------------------------------------------------
    # modes
    def initial_relations(self) -> tuple:
        rels = super().initial_relations()
        if getattr(self, "_snepslog_initialized", False) and "r" not in rels:
            return ("r",) + tuple(rels)
        return rels

    def define_if_not_yet_defined(self, arc: str) -> None:
        if not self.is_r(arc):
            self.new_r(arc)

    def set_mode(self, mode: int) -> None:
        self.snepslog_mode = mode
        if mode == 1:
            self.define_if_not_yet_defined("r")
        self.br_auto_mode = False
        self.br_tie_mode = False
        self.br_totalorder = self.br_orders["null-order"]

    def in_mode3(self) -> bool:
        return self.snepslog_mode == 3

    def set_mode_3(self, silent: bool = False) -> None:
        self.resetnet(True)
        self.silent_mode3 = silent
        self.snepslog_mode = 3
        self.propargs.clear()
        self.argsprop.clear()
        if not silent:
            self.write("\nIn SNePSLOG Mode 3.\nUse define-frame <pred> <list-of-arc-labels>.\n\n")
        for pred, arcs, desc in MODE3_FRAMES:
            self.define_frame(self.fold_name(pred), [a or None for a in arcs], desc)
        for arcs, desc in SNIP_ARC_DESCRIPTIONS:
            self.make_description_function(tuple([None] + arcs), desc)
        self.br_tie_mode = True
        self.br_auto_mode = True
        self.br_totalorder = self.br_orders["fluent"]

    def relation_predicate(self, node: Node) -> Any:
        if self.snepslog_mode == 1:
            return node.nodeset("r")
        if self.snepslog_mode == 2:
            arc = self._predicate_arc(node)
            return node.nodeset(arc) if arc else ()
        cf = tuple(r for r in node.fcableset if self.isdn_r(r))
        if cf not in self.argsprop:
            return None
        choice = self.argsprop[cf]
        if isinstance(choice, list):
            return choice[0]
        ns = node.nodeset(choice)
        if not ns:
            return None
        sv = ns[0].snepslog
        if isinstance(sv, dict):
            pred = sv.get("snepslog-version")
        elif sv is None:
            pred = ns[0].name
        else:
            pred = sv
        return pred

    def _predicate_arc(self, node: Node) -> Optional[str]:
        for r in node.fcableset:
            if r.startswith(" "):
                return r
        return None

    def relation_argument_list(self, node: Node) -> list:
        if self.snepslog_mode == 1:
            out = []
            k = 1
            while True:
                ns = node.nodeset(f"a{k}")
                if not ns:
                    return out
                out.append(ns)
                k += 1
        if self.snepslog_mode == 2:
            arc = self._predicate_arc(node)
            out = []
            for a in self.associated_arcs.get(arc, []):
                out.extend(node.nodeset(a))
            return out
        pred = self.relation_predicate(node)
        arcs = self.propargs.get(_name(pred), [None])
        return [node.nodeset(a) for a in arcs[1:]]

    def make_relation(self, action: str, relation: Any, arguments: list) -> list:
        if self.snepslog_mode == 1:
            self.define_if_not_yet_defined("r")
            out = [action, "r", relation]
            for k, x in enumerate(arguments, 1):
                arc = f"a{k}"
                self.define_if_not_yet_defined(arc)
                out.extend([arc, x])
            return out
        if self.snepslog_mode == 2:
            rname = _name(relation[1]) if isinstance(relation, list) else _name(relation)
            rel_arc = f" rel {rname}"
            arg_arcs = [f"rel-arg#{rname}{k}" for k in range(1, len(arguments) + 1)]
            for a in [rel_arc] + arg_arcs:
                self.define_if_not_yet_defined(a)
            self.associated_arcs[rel_arc] = arg_arcs
            out = [action]
            for arc, x in zip([rel_arc] + arg_arcs, [relation] + list(arguments)):
                out.extend([arc, x])
            return out
        arcs = self.propargs.get(_name(relation) if not isinstance(relation, list) else None)
        out = [action]
        if arcs:
            for arc, arg in zip(arcs, [relation] + list(arguments)):
                if arc:
                    out.extend([arc, arg])
        return out

    def define_frame(self, pred: str, list_of_args: Any, desc: Optional[str] = None) -> None:
        args = [_name(a) if a is not None and not (isinstance(a, str) and a.lower() == "nil")
                else None for a in _as_list(list_of_args)]
        ordered = tuple(sorted(args if args[0] else args[1:], key=self.rel_sort_key))
        if pred in self.propargs and ordered in self.argsprop:
            self.fresh_line()
            self.write(f"WARNING: {pred} is already associated with the same case-frame. "
                       "Ignoring\nredeclaration.\n")
            return
        if pred in self.propargs:
            raise SNePSError(f"{pred} is already associated with the case-frame "
                             f"{self.propargs[pred]}.")
        predchoice = args[0] if args[0] else [pred]
        for a in ordered:
            self.define_if_not_yet_defined(a)
        if ordered in self.argsprop and self.argsprop[ordered] != predchoice:
            raise SNePSError(f"The case-frame {list(ordered)} is already used for "
                             f"{self.argsprop[ordered]}.")
        self.propargs[pred] = args
        self.argsprop[ordered] = predchoice
        if desc:
            key = ((pred,) if args[0] else (None,)) + ordered
            self.make_description_function(key, desc)
        if not self.silent_mode3:
            self._frame_feedback(pred, args)

    def _frame_feedback(self, pred: str, args: list) -> None:
        self.fresh_line()
        n = len(args) - 1
        text = pred + "(" + ",".join(f"x{i}" for i in range(1, n + 1)) + ")"
        text += " will be represented by {"
        if args[0]:
            text += f"<{args[0]}, {pred}>"
            if len(args) > 1 and args[1]:
                text += f", <{args[1]}, x1>"
        else:
            text += f"<{args[1]}, x1>"
        for i, arc in enumerate(args[2:], 2):
            text += f", <{arc}, x{i}>"
        self.write(text + "}\n")

    # -- descriptions ------------------------------------------------------------
    def make_description_function(self, key: tuple, desc: str) -> None:
        arcs = []
        text = desc
        while "[" in text:
            lb = text.index("[")
            rb = text.index("]")
            arcs.append(text[lb + 1:rb].strip())
            text = text[:lb] + "\0" + text[rb + 1:]
        unknown = [a for a in arcs if a not in key]
        if unknown:
            raise SNePSError(f"{unknown} are not arcs in this caseframe.")
        parts = text.split("\0")

        def describe(n: Node) -> str:
            out = [parts[0]]
            for arc, tail in zip(arcs, parts[1:]):
                out.append(self._node_set_description(n.nodeset(arc)))
                out.append(tail)
            return "".join(out)
        self.argsdesc[key] = describe

    def _node_set_description(self, ns: tuple) -> str:
        if len(ns) == 1:
            return self.get_node_description_string(ns[0])
        if len(ns) == 2:
            return (self.get_node_description_string(ns[0]) + " and "
                    + self.get_node_description_string(ns[1]))
        if not ns:
            return ""
        out = ""
        rest = list(ns)
        while len(rest) > 2:
            out += self.get_node_description_string(rest[0]) + ", "
            rest = rest[1:]
        return (out + self.get_node_description_string(rest[0]) + ", and "
                + self.get_node_description_string(rest[1]))

    def get_node_description_string(self, n: Node) -> str:
        if n.is_not():
            args = [self.get_node_description_string(a) for a in n.nodeset("arg")]
            return "it is not the case that " + _english_and(args)
        if n.is_base:
            return n.name
        if n.is_var:
            return _name(n.snepslog) or n.name
        arcs = tuple(r for r in n.fcableset if not r.endswith("-"))
        pred = None
        sv = n.snepslog
        if isinstance(sv, dict) and isinstance(sv.get("snepslog-version"), list) and \
                sv["snepslog-version"]:
            pred = _name(sv["snepslog-version"][0])
        fn = self.argsdesc.get((pred,) + arcs) or self.argsdesc.get((None,) + arcs)
        return fn(n) if fn else "<not-yet-specified-by-user>"

    def describe_terms(self, nodes: Iterable[Node]) -> None:
        for n in nodes or ():
            s = self.get_node_description_string(n)
            self.write((s[:1].upper() + s[1:]) + ".\n")

    def closed_terms(self) -> list:
        out = []
        for n in self.all_nodes():
            if n.is_mol and not n.is_pat:
                out.insert(0, n)
        return out

    # ------------------------------------------------------------------
    # printing
    def snepslog_print(self, nodes: Any, stream: Optional[OutputStream] = None) -> None:
        out = stream or self.outunit
        out.write(self.snepslog_string(nodes))

    def snepslog_string(self, nodes: Any) -> str:
        if isinstance(nodes, list) and nodes and all(isinstance(x, list) for x in nodes):
            result = ""
            for sub in nodes:
                result += "("
                for var, val in sub:
                    result += "(?" + (_name(var) or "") + " . " + printer(self.generator.gen(val)) + ")"
                result += ")\n"
            return result
        if nodes is None:
            return ""
        items = list(nodes) if isinstance(nodes, (list, tuple)) else [nodes]
        entries: list = []
        for node in items:
            if not isinstance(node, Node):
                continue
            if self.complete_description != "unlabeled":
                entries.append(m_to_wff(node) + ("!:" if self.isassert(node) else ": "))
            else:
                entries.append("")
            entries.append(printer(self.generator.gen(node)))
            entries.append(printer(self.generator.derivation_histories(node))
                           if self.complete_description == "expert" else "")
            entries.append("\n")
        return "".join("  " + e for e in entries)

    def node_text(self, node: Node) -> str:
        """The SNePSLOG text of NODE (without the wff label)."""
        return printer(self.generator.gen(node))

    # hooks used by SNIP/SNeBR tracing while SNePSLOG runs
    def surface(self, nodes: Iterable[Node]) -> None:
        if self.snepslog_running:
            self.snepslog_print(list(nodes))
        else:
            super().surface(nodes)

    def surface_string(self, node: Node) -> str:
        return self.snepslog_string([node])

    def slight_describe_or_surface(self, n: Any, stream: Any = None) -> Any:
        if self.snepslog_running and isinstance(n, Node):
            return m_to_wff(n)
        return super().slight_describe_or_surface(n, stream)

    def surface_to_string(self, node: Node) -> str:
        if self.snepslog_running:
            return self.snepslog_string([node])
        return super().surface_to_string(node)

    def node_label(self, n: Node) -> str:
        return m_to_wff(n) if self.snepslog_running else str(n)

    def list_contexts(self) -> None:
        for ct in sorted(self.contexts.values(), key=lambda c: -c.order):
            for name in ct.names:
                self.fresh_line()
                self.write(f"{name}\n")

    # ------------------------------------------------------------------
    # reading
    def _sl_next_char(self) -> tuple[Optional[str], bool]:
        stream = self.inunit
        while True:
            if self._sl_stream is not stream or self._sl_line is None:
                if stream is None:
                    return None, True
                line, _missing = stream.read_line()
                self._sl_stream = stream
                if line is None:
                    self._sl_line = None
                    return None, True
                if line == "":
                    self._sl_line = None
                    continue
                self._sl_line = line
                self._sl_index = 0
            line = self._sl_line
            i = self._sl_index
            if i > len(line):
                self._sl_line = None
                continue
            if i == len(line):
                self._sl_index += 1
                return "\n", False
            if i == len(line) - 1 and line[i] == "\\":
                self._sl_line = None
                continue
            self._sl_index += 1
            return line[i], False

    def _sl_put_back(self) -> None:
        if self._sl_stream is self.inunit and self._sl_index > 0:
            self._sl_index -= 1

    def snepslog_read_string(self) -> Optional[str]:
        result: list = []
        stack: list = []
        real = False
        while True:
            c, eof = self._sl_next_char()
            if eof:
                if result and "".join(result).strip():
                    self.write("Warning: Eof Unexpected")
                return None
            if stack and c == stack[-1]:
                stack.pop()
                result.append(c)
            elif c in "({":
                real = True
                stack.append(")" if c == "(" else "}")
                result.append(c)
            elif c in ")}":
                self._sl_line = None
                raise SNePSError("Error in snepslog read. Unexpected eof of sequence found",
                                 "snepslog", "read")
            elif c == ";":
                inside = bool(stack)
                while True:
                    if c is None or c == "\n":
                        if not real or inside:
                            if c is not None:
                                result.append(c)
                        else:
                            self._sl_put_back()
                        break
                    if c == "\\":
                        c, _ = self._sl_next_char()
                        result.append(c or "")
                    else:
                        result.append(c)
                    c, eof = self._sl_next_char()
                    if eof:
                        c = None
            elif c == "\\":
                c2, _ = self._sl_next_char()
                result.append(c2 or "")
            elif c == '"':
                real = True
                result.append(c)
                while True:
                    c2, eof = self._sl_next_char()
                    if eof:
                        break
                    result.append(c2)
                    if c2 == '"':
                        break
            elif c == "\n" and real and not stack:
                result.append(c)
                return "".join(result)
            else:
                if c not in " \n\t":
                    real = True
                result.append(c)

    def snepslog_read(self) -> tuple[Any, bool]:
        """Read and parse one SNePSLOG input; returns (form, eof)."""
        if self._input_stack and self.inunit is not None and self.inunit.at_eof() \
                and (self._sl_line is None or self._sl_index > len(self._sl_line)):
            self._end_demo()
            return None, False
        in_demo = bool(self._input_stack)
        if in_demo and self.demo_pause_point("before") == "exit":
            return None, False
        text = self.snepslog_read_string()
        if text is None:
            if self._input_stack:
                return None, False
            return None, True
        form = self.snepslog_parser.parse(text)
        if in_demo and self._input_stack and self.demo_pause_point("after") == "exit":
            return None, False
        return form, False

    # ------------------------------------------------------------------
    # the top level
    def snepslog_repl(self, inunit: Optional[InputStream] = None,
                      outunit: Optional[OutputStream] = None, hello: Any = True) -> None:
        """Run the SNePSLOG read-eval-print loop (until ``exit`` or the end of
        the input)."""
        import sys
        old = (self.inunit, self.outunit, self.snepslog_running, self.infertrace)
        if inunit is not None:
            self.inunit = inunit
        elif self.inunit is None:
            self.inunit = InputStream.from_textio(sys.stdin)
        if outunit is not None:
            self.outunit = outunit
        self.snepslog_running = True
        self.infertrace = "surface" if self.infertrace else None
        try:
            if hello is True:
                self.write("\n   Welcome to SNePSLOG (A logic interface to SNePS)\n\n"
                           "PySNePS: SNePS 2.8 translated to Python.\n"
                           "Type `copyright' for copyright information.\n"
                           "Type `demo' for a list of example applications.\n\n")
            elif isinstance(hello, str) and hello:
                self.write(f"\n{hello}\n")
            self._snepslog_initialized = True
            if "r" not in self.converses:
                self.define_if_not_yet_defined("r")
            self.snepslog_loop()
            self.write("\nBye\n")
        finally:
            infertrace = self.infertrace
            self.inunit, self.outunit, self.snepslog_running, _ = old
            self.infertrace = infertrace if old[3] else old[3]

    def snepslog_loop(self) -> None:
        from ..snepsul.evaluator import Result
        while True:
            ct = self.get_context(self.crntct)
            if ct is not None and ct.okinconsistent:
                self.write("*")
            self.write(f"{self.snepslog_prompt} ")
            try:
                command, eof = self.snepslog_read()
            except SnepslogEnd:
                return
            except SNePSError as e:
                self._report_sneps_error(e)
                continue
            if eof:
                return
            if self.trace_translation and command is not None:
                self.fresh_line()
                self.write(f"Translation: {flat_text(command)}\n")
            t0 = time.process_time()
            try:
                res = self.topsneval(command)
            except SNePSError as e:
                self.fresh_line()
                self.write(f"Error: {e}\n")
                res = Result()
            except Exception as e:  # keep the top level alive
                self.fresh_line()
                self.write(f"Error: {type(e).__name__}: {e}\n")
                res = Result()
            t1 = time.process_time()
            self.fresh_line()
            self.write("\n")
            self.snepslog_print(res.value)
            self.set_sv("lastcommand", command)
            self.sneps_timer(t0, t1)

    # ------------------------------------------------------------------
    # files and demos
    def snepslog_demo(self, file: Optional[str], pause: Any = None) -> None:
        if file is None:
            self.demo_menu(snepslog=True)
            return
        if pause is None:
            self.start_demo(file)
        else:
            self.start_demo(file, pause)

    def snepslog_load(self, file: str) -> None:
        """Execute a file of SNePSLOG commands silently (batching assertions)."""
        path = self.translate_path(file)
        if self.snepslog_running:
            self.start_demo(path, output=NullOutputStream(), use_batch_assert=True)
            return
        self.assert_later += 1
        try:
            text = open(path, encoding="utf-8", errors="replace").read()
            self.snepslog_repl(inunit=InputStream(text=text + "\nexit\n"),
                               outunit=NullOutputStream(), hello=False)
        finally:
            props = self.new_propositions
            self.new_propositions = []
            self.assert_later -= 1
            self.batch_assert(props)

    def demo_menu(self, snepslog: bool = False) -> None:
        from .demos import demo_menu
        demo_menu(self, snepslog)

    # ------------------------------------------------------------------
    # the Python tell/ask interface
    def snepslog_eval(self, text: str) -> Any:
        """Parse and evaluate one SNePSLOG input; returns the result."""
        old_running = self.snepslog_running
        self.snepslog_running = True
        try:
            form = self.snepslog_parser.parse(text)
            res = self.topsneval(form)
        except SnepslogEnd:
            return None
        finally:
            self.snepslog_running = old_running
        return res.value

    def tell(self, text: str, *args: Any, quiet: bool = True) -> Any:
        """Give TEXT (one or more lines of SNePSLOG) to SNePSLOG.  With ARGS,
        ``{}`` fields in TEXT are replaced by them (nodes by their wff names).

        Returns the nodes asserted, built or deduced by the last input."""
        if args:
            text = text.format(*[m_to_wff(a) if isinstance(a, Node) else a for a in args])
        result: Any = None
        out = NullOutputStream() if quiet else self.outunit
        old_in = self.inunit
        with self.let(outunit=out):
            self.inunit = InputStream(text=text if text.endswith("\n") else text + "\n")
            self._sl_line = None
            try:
                while True:
                    s = self.snepslog_read_string()
                    if s is None:
                        break
                    result = self.snepslog_eval(s)
                    if not quiet and result is not None:
                        self.snepslog_print(result)
            finally:
                self.inunit = old_in
                self._sl_line = None
        return result

    def _ask_command(self, fn: str, text: str) -> Any:
        if text and text.rstrip()[-1:] not in (".", "!", "?"):
            text = text + "?"
        old_running = self.snepslog_running
        self.snepslog_running = True
        try:
            form = self.snepslog_parser.parse(text)
        finally:
            self.snepslog_running = old_running
        if isinstance(form, list) and form and isinstance(form[0], str):
            if form[0].lower() == "deduce":
                form = [fn] + form[1:]
            elif form[0].lower() == "findassert" and fn in ("deducewh", "deducewhnot"):
                form = [fn, [0, 0]] + [
                    ["$", e[1]] if isinstance(e, list) and len(e) == 2 and e[0] == "?" else e
                    for e in form[1:]]
        return self.topsneval(form).value

    def ask(self, text: str, verbose: bool = False) -> list:
        """Ask whether TEXT holds (DEDUCETRUE); returns the deduced nodes."""
        with self.let(outunit=self.outunit if verbose else NullOutputStream()):
            res = self._ask_command("deducetrue", text)
            if verbose:
                self.snepslog_print(res)
        return list(res or ())

    def askifnot(self, text: str, verbose: bool = False) -> list:
        """Ask whether the negation of TEXT holds (DEDUCEFALSE)."""
        with self.let(outunit=self.outunit if verbose else NullOutputStream()):
            res = self._ask_command("deducefalse", text)
            if verbose:
                self.snepslog_print(res)
        return list(res or ())

    def askwh(self, text: str, verbose: bool = False) -> list:
        """Ask a wh-question; returns a list of {variable: node} substitutions."""
        with self.let(outunit=self.outunit if verbose else NullOutputStream()):
            res = self._ask_command("deducewh", text)
            if verbose:
                self.snepslog_print(res)
        return _wh_dicts(res)

    def askwhnot(self, text: str, verbose: bool = False) -> list:
        with self.let(outunit=self.outunit if verbose else NullOutputStream()):
            res = self._ask_command("deducewhnot", text)
            if verbose:
                self.snepslog_print(res)
        return _wh_dicts(res)

    def _request_new_hyp(self) -> Optional[Node]:
        if not self.snepslog_running:
            return super()._request_new_hyp()
        self.write("\n Enter a hypothesis using SNePSLOG all on one line and ending with a "
                   "period: ")
        while True:
            self.write("\n=><= ")
            text = self.snepslog_read_string()
            if text is None:
                return None
            form = self.snepslog_parser.parse(text)
            if isinstance(form, list):
                form = form + [":context", self.crntct]
            ns = self.topsneval(form).value
            if ns:
                return ns[0]
            self.write("\n Oops... something went wrong\n Would you try to enter again?")
            if not self._user_says_yes():
                return None


def _wh_dicts(res: Any) -> list:
    out = []
    for sub in res or []:
        d = {}
        for var, val in sub:
            d[_name(var) if not isinstance(var, Node) else var.name] = val
        out.append(d)
    return out


def _as_list(x: Any) -> list:
    if x is None:
        return []
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _english_and(items: list) -> str:
    """ITEMS joined as in "a, b and c"."""
    out = []
    for k, x in enumerate(items):
        out.append(x)
        rest = len(items) - k - 1
        if rest == 1:
            out.append(" and ")
        elif rest > 1:
            out.append(", ")
    return "".join(out)


# ----------------------------------------------------------------------
# epistemic entrenchment orders

def _fluent_order(net: Any, lhs: Node, rhs: Node) -> bool:
    return _is_fluent(net, lhs) or not _is_fluent(net, rhs)


def _is_fluent(net: Any, n: Node) -> bool:
    pred = net.relation_predicate(n)
    if isinstance(pred, (tuple, list)):
        name = pred[0].name if pred else None
    else:
        name = _name(pred)
    return name is not None and name in [net.fold_name(str(f)) for f in net.fluents]


def _source_order(net: Any, p1: Node, p2: Node) -> bool:
    if p1 is p2:
        return True
    s1 = [d.get("x") for d in net.askwh(f"HasSource({m_to_wff(p1)}, ?x)")]
    s2 = [d.get("x") for d in net.askwh(f"HasSource({m_to_wff(p2)}, ?x)")]
    if s1 and s2:
        return not all(any(a is not b and net.ask(f"IsBetterSource({m_to_wff(a)}, {m_to_wff(b)})")
                           for a in s1) for b in s2)
    return not s2


def _explicit_order(net: Any, lhs: Node, rhs: Node) -> bool:
    return not net.ask(f"IsLessEntrenched({m_to_wff(rhs)}, {m_to_wff(lhs)})")
