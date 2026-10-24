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
"""The SNePSLOG parser (SNePS 2.8 ``snepslog/parser``).

Translates one SNePSLOG input string into what the SNePSUL top level
evaluates: a SNePSUL form (Python lists and names) for wffs and the commands
that SNePSUL provides, or a Python callable for SNePSLOG's own commands.
The grammar is recognized by recursive descent over the remaining input
text, exactly as in SNePS.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..core.printing import Text, flat_text
from ..io.streams import InputStream
from ..snepsul.reader import EOF, ReaderError, SnepsulReader, read_from_string

WHITESPACE = " \n\t\f\r"
TERMINAL_PUNCTUATION = ")}"
SEPARATING_PUNCTUATION = "({,"
PUNCTUATION = WHITESPACE + TERMINAL_PUNCTUATION + SEPARATING_PUNCTUATION + ".!?"

BUILD = "build"
QMARK = "?"
STAR = "*"
DOLLAR = "$"
PLUS = "+"


class SNePSLOGParseError(Exception):
    def __init__(self, msg: str):
        super().__init__(msg)
        self.msg = msg


class Parser:
    """Parses SNePSLOG input for one SNePSLOG session (a Network)."""

    def __init__(self, net: Any):
        self.net = net
        self.inp = ""

    # ------------------------------------------------------------------
    # entry point
    def parse(self, text: str) -> Any:
        """SNEPSLOG-READ-FROM-STRING"""
        self.inp = text
        self.pop_input(0)
        if self.empty():
            return None
        try:
            expr = self.wff_name_command() or self.snepslog_command() or self.wff_command()
            if expr is not None and expr is not False:
                if self.empty():
                    return expr
                self.error(f"Extra text in input: {_s(self.inp)}")
            self.error(f"Unrecognized input: {_s(self.inp)}")
        except SNePSLOGParseError as e:
            self.net.fresh_line()
            self.net.write(f"Warning: {e.msg}\nContinue with SNePSLOG\n")
            return None

    def error(self, msg: str) -> None:
        raise SNePSLOGParseError(msg)

    # ------------------------------------------------------------------
    # utilities
    def empty(self) -> bool:
        return self.inp == ""

    def first_charp(self, c: str) -> bool:
        return self.inp != "" and self.inp[0] == c

    def pop_input(self, n: int) -> str:
        out = self.inp[:n]
        self.inp = self.inp[n:].lstrip(WHITESPACE)
        while self.first_charp(";"):
            k = self.inp.find("\n")
            if k < 0:
                self.inp = ""
            else:
                self.inp = self.inp[k + 1:].lstrip(WHITESPACE)
        return out

    def have_command(self, command: str, has_arg: bool = False) -> bool:
        n = len(command)
        if len(self.inp) >= n and self.inp[:n].lower() == command.lower():
            if has_arg:
                self.pop_input(n)
                return True
            return self.empty_input_after(n)
        return False

    def empty_input_after(self, n: int) -> bool:
        init = self.pop_input(n)
        if self.empty() or self.inp[0] == ".":
            self.inp = ""
            return True
        self.inp = init + self.inp
        return False

    def get_form(self, snepsul: bool = False) -> Any:
        """Read one parenthesised expression (or atom) from the input; with
        SNEPSUL, in SNePSUL syntax."""
        stream = InputStream(text=self.inp)
        try:
            form = SnepsulReader(stream, self.net.fold_case, macros=snepsul).read()
        except ReaderError as e:
            self.error(str(e))
        if form is EOF:
            self.error("end of input")
        self.pop_input(stream._pos)
        return form

    def atom(self) -> tuple[Any, int]:
        """The atom at the start of the input (a name, number or string) and
        its length."""
        if self.inp[0] == '"' or self.inp[0] not in PUNCTUATION:
            stream = InputStream(text=self.inp)
            try:
                obj = SnepsulReader(stream, self.net.fold_case, macros=False,
                                    extra_terminating="{}!?").read()
            except ReaderError as e:
                self.error(str(e))
            return obj, stream._pos
        return None, 0

    def return_forms(self, *forms: Any) -> Callable[[], Any]:
        """A SNePSLOG command as a Python callable: it runs FORMS (callables,
        or SNePSUL command forms) and has an empty node set as its value."""
        net = self.net

        def command() -> Any:
            from ..snepsul.evaluator import Result
            for f in forms:
                if callable(f):
                    f()
                else:
                    net.call_command(f)
            return Result((), net.value_sv("defaultct"))
        return command

    # ------------------------------------------------------------------
    # symbols and names
    def snepslog_symbol(self) -> Any:
        if self.inp == "" or self.inp[0] in SEPARATING_PUNCTUATION or self.inp[0] in PUNCTUATION:
            return None
        token, n = self.atom()
        self.inp = self.inp[n:].lstrip(WHITESPACE)
        if token is EOF or token is None:
            return None
        if isinstance(token, Text):
            return str(token)
        if isinstance(token, (int, float)) and not isinstance(token, bool) or \
                type(token).__name__ == "Fraction":
            from ..core.node import number_name
            return number_name(token)
        if token is True:
            return "t"
        return token

    def wff_name(self) -> Any:
        if len(self.inp) > 3 and self.inp[:3].lower() == "wff":
            end = next((k for k, c in enumerate(self.inp) if c in PUNCTUATION), len(self.inp))
            token_text = self.inp[:end]
            tail = token_text[3:]
            if tail.isdigit() and self.net.node("M" + tail) is not None:
                self.pop_input(end)
                if self.first_charp("!") and len(self.inp.rstrip(" \t\n")) > 1:
                    self.pop_input(1)
                return "M" + tail
        return None

    def qmark(self) -> bool:
        if self.first_charp("?"):
            self.pop_input(1)
            return True
        return False

    def qvar(self) -> Any:
        if self.qmark():
            var = self.snepslog_symbol()
            if var is not None:
                return [QMARK, var]
        return None

    def check_is_context_name(self, cname: Any) -> bool:
        from ..core.context import Context
        if isinstance(self.net.value_sv(_name(cname)), Context):
            return True
        self.error(f"The symbol {_name(cname)} is not the name of a context at {_s(self.inp)}")
        return False

    # ------------------------------------------------------------------
    # commands
    def snepslog_command(self) -> Any:
        c = self.inp[0]
        fn = {"%": self.percent_command, "^": self.caret_command, "a": self.a_command,
              "b": self.b_command, "c": self.c_command, "d": self.d_command,
              "e": self.e_command, "l": self.l_command, "n": self.n_command,
              "p": self.p_command, "r": self.r_command, "s": self.s_command,
              "t": self.t_command, "u": self.u_command}.get(c)
        return fn() if fn is not None else None

    def a_command(self) -> Any:
        if self.inp[:3].lower() == "ask":
            return self.ask_command()
        if self.have_command("activate!", True):
            return ["activate", ["assert"] + self.required_wff_arg("activate!")[1:]]
        if self.have_command("activate", True):
            trm = self.wff()
            if trm is not None:
                self.have_command(".")
                return ["activate", trm]
            self.error(f"The command activate requires a term as an argument at: {_s(self.inp)}")
        if self.have_command("add-to-context", True):
            cname = self.snepslog_symbol()
            if cname is not None and self.check_is_context_name(cname):
                hyps = self.term_set()
                self.have_command(".")
                if not isinstance(hyps, list) or (hyps and _is(hyps[0], "build")):
                    hyps = [hyps]
                forms = []
                for cmd in hyps:
                    if not isinstance(cmd, list):
                        self.net.assert_n(self.net.node(_name(cmd)), _name(cname))
                        forms.append(cmd)
                    else:
                        forms.append(["assert"] + cmd[1:] + [":context", cname])
                return [PLUS] + forms
            self.error("The command add-to-context requires a context name as an argument at: "
                       f"{_s(self.inp)}")
        return None

    def ask_command(self) -> Any:
        for cmd, fn in (("askifnot", "deducefalse"), ("askwhnot", "deducewhnot"),
                        ("askwh", "deducewh"), ("ask", "deducetrue")):
            if self.have_command(cmd, True):
                return self.fix_qvars_for_deduce([fn] + self.required_wff_arg(cmd)[1:])
        return None

    def b_command(self) -> Any:
        net = self.net
        if self.have_command("beliefs-about", True):
            terms = self.p_term_set()
            if not isinstance(terms, list) or (terms and (_is(terms[0], "find") or _is(terms[0], "+"))):
                return ["beliefs-about", terms]
            return [PLUS, [["beliefs-about", ns] for ns in terms]]
        if self.have_command("br-mode", True):
            if self.empty_input_after(0):
                msg = ("Belief revision mode currently set to 'auto'" if net.br_auto_mode
                       else "Belief revision mode currently set to 'manual'")
                return self.return_forms(_writer(net, msg))
            if self.have_command("auto"):
                return self.return_forms(["br-mode", True],
                                         _writer(net, "Belief revision mode will now be set to 'auto'."))
            if self.have_command("manual"):
                return self.return_forms(["br-mode", None],
                                         _writer(net, "Belief revision mode will now be set to 'manual'."))
            self.error("The command br-mode can only accept 'auto' or 'manual' as an argument")
        if self.have_command("br-tie-mode", True):
            if self.empty_input_after(0):
                msg = ("Belief revision tie mode currently set to 'auto'" if net.br_tie_mode
                       else "Belief revision tie mode currently set to 'manual'")
                return self.return_forms(_writer(net, msg))
            if self.have_command("auto"):
                return self.return_forms(["br-tie-mode", True],
                                         _writer(net, "Entrenchment ties will now be broken automatically"))
            if self.have_command("manual"):
                return self.return_forms(["br-tie-mode", None],
                                         _writer(net, "The user will be consulted when an entrenchment tie occurs."))
            self.error("The command br-tie-mode can only accept 'auto' or 'manual' as an argument")
        return None

    def d_command(self) -> Any:
        net = self.net
        if self.have_command("describe-context", True):
            cname = self.snepslog_symbol()
            if cname is not None:
                self.check_is_context_name(cname)
            self.have_command(".")
            return ["describe-context", cname]
        if self.have_command("define-frame", True):
            return self.define_frame_command()
        if self.have_command("define-path", True):
            return self.define_path_command()
        if self.have_command("demo", True):
            filename = self.path()
            pause = self.snepslog_symbol()
            if pause is not None and _name(pause).lower() not in ("t", "b", "bv", "a", "av", "n"):
                self.error(f"Unrecognized pause control, {_name(pause)}, at: {_s(self.inp)}")
            self.have_command(".")
            if pause is not None:
                return self.return_forms(lambda: net.snepslog_demo(filename, _name(pause).lower()))
            if filename is not None:
                return self.return_forms(lambda: net.snepslog_demo(filename, None))
            return self.return_forms(lambda: net.demo_menu(snepslog=True))
        if self.have_command("describe-terms", True):
            result = self.p_term_set()
            if result is None:
                return self.return_forms(lambda: net.describe_terms(net.closed_terms()))
            form = result if isinstance(result, list) else [PLUS, result]
            return self.return_forms(lambda: net.describe_terms(net.nseval(form)))
        return None

    def define_frame_command(self) -> Any:
        pred = self.snepslog_symbol()
        if pred is not None and self.first_charp("("):
            caseframe = self.get_form()
            if self.first_charp('"'):
                desc = self.get_form()
                self.have_command(".")
                return self.return_forms(lambda: self.net.define_frame(_name(pred), caseframe, desc))
            self.have_command(".")
            return self.return_forms(lambda: self.net.define_frame(_name(pred), caseframe))
        self.error("The command define-frame requires a predicate and a list of relations at: "
                   f"{_s(self.inp)}")

    def define_path_command(self) -> Any:
        if self.empty():
            self.error("The command define-path needs a relation and a path, but has neither.")
        rel = self.get_form()
        if not self.net.is_r(_name(rel)):
            self.error(f"The command define-path was called on {_name(rel)}, which is not a relation.")
        if self.empty():
            self.error(f"The command define-path on relation {_name(rel)} is missing a path.")
        path = self.get_form()
        if path is None:
            self.error(f"The command define-path on the relation {_name(rel)} is missing a path at: "
                       f"{_s(self.inp)}")
        self.have_command(".")
        return ["define-path", rel, path]

    def path(self) -> Optional[str]:
        self.inp = self.inp.rstrip(WHITESPACE)
        end = len(self.inp)
        if end > 0 and self.inp[end - 1] == ".":
            end -= 1
        stream = InputStream(text=self.inp[:end])
        try:
            obj = SnepsulReader(stream, self.net.fold_case, macros=False).read()
        except ReaderError as e:
            self.error(str(e))
        self.pop_input(stream._pos)
        if obj is EOF or obj is None:
            return None
        return obj if isinstance(obj, str) else flat_text(obj)

    def l_command(self) -> Any:
        net = self.net
        if self.have_command("list-contexts"):
            self.have_command(".")
            net.list_contexts()
            return self.return_forms()
        if self.have_command("list-wffs"):
            def list_wffs() -> None:
                for node in net.all_nodes():
                    if node.asupport:
                        net.snepslog_print([node])
            return self.return_forms(list_wffs)
        if self.have_command("list-terms", True):
            return self.p_term_set() or (lambda: list(net.closed_terms()))
        if self.have_command("list-asserted-wffs", True):
            cname = self.snepslog_symbol()
            cname = _name(cname) if cname is not None else net.value_sv("defaultct")
            self.check_is_context_name(cname)
            self.have_command(".")

            def list_asserted() -> None:
                with net.let(crntct=cname):
                    for node in net.all_nodes():
                        if node.asupport and net.isassert(node):
                            net.snepslog_print([node])
            return self.return_forms(list_asserted)
        if self.have_command("load", True):
            filename = self.path()
            if filename is None:
                self.error(f"The command load must have a file as an argument at: {_s(self.inp)}")
            self.have_command(".")
            return self.return_forms(lambda: net.snepslog_load(filename))
        return None

    def p_term_set(self) -> Any:
        have_set = self.first_charp("{")
        patterns = self.term_set() if not self.empty() else None
        self.have_command(".")
        if patterns is None:
            return None
        if have_set:
            return [PLUS] + [["find"] + f[1:] if isinstance(f, list) else f for f in patterns]
        if isinstance(patterns, list):
            return ["find"] + patterns[1:]
        return patterns

    def p_command(self) -> Any:
        if self.have_command("perform", True):
            act = self.atomic_term()
            if act is not None:
                self.have_command(".")
                return ["perform", act]
            self.error(f"The command perform needs an argument at: {_s(self.inp)}")
        return None

    def r_command(self) -> Any:
        if self.have_command("remove-from-context", True):
            cname = self.snepslog_symbol()
            if cname is not None and self.check_is_context_name(cname):
                hyps = self.p_term_set()
                return ["remove-from-context", hyps, cname]
            self.error("The command remove-from-context requires a context name as an argument "
                       f"at: {_s(self.inp)}")
        return None

    def s_command(self) -> Any:
        net = self.net
        if self.inp[:4].lower() == "set-":
            if self.inp[4:9].lower() == "mode-":
                if self.have_command("set-mode-1"):
                    return self.return_forms(["resetnet", True], lambda: net.set_mode(1))
                if self.have_command("set-mode-2"):
                    return self.return_forms(["resetnet", True], lambda: net.set_mode(2))
                if self.have_command("set-mode-3", True):
                    arg = self.snepslog_symbol()
                    self.have_command(".")
                    silent = arg is not None and _name(arg).lower() not in ("nil",)
                    return self.return_forms(lambda: net.set_mode_3(silent))
                return None
            if self.have_command("set-context", True):
                cname = self.snepslog_symbol()
                if cname is not None:
                    hyps = self.p_term_set()
                    self.have_command(".")
                    return ["set-context", hyps, cname]
                self.error("The command set-context requires a context name as an argument at: "
                           f"{_s(self.inp)}")
            if self.have_command("set-default-context", True):
                cname = self.snepslog_symbol()
                if cname is not None:
                    self.check_is_context_name(cname)
                    self.have_command(".")
                    return ["set-default-context", cname]
                self.error("The command set-default-context requires a context name as an "
                           f"argument at: {_s(self.inp)}")
            if self.have_command("set-order", True):
                sym = self.snepslog_symbol()
                name = _name(sym).lower() if sym is not None else "null-order"
                msgs = {"null-order": "All propositions will be equally epistemically entrenched.",
                        "fluent": "Fluents will be less epistemically entrenched than non-fluents.",
                        "source": "IsBetterSource(s1,s2) will mean that s1 is more credible than s2.",
                        "explicit": "IsLessEntrenched(p1,p2) will mean that p1 is strictly less "
                                    "entrenched than p2."}
                net.write(msgs.get(name, f"{_name(sym)}(p, q) will mean that p is less or equally "
                                         "epistemically entrenched as q."))
                return self.return_forms(["set-order", sym])
            return None
        if self.have_command("show", True):
            return ["show", self.p_term_set() or [STAR, "nodes"]]
        return None

    def t_command(self) -> Any:
        return self._trace_command("trace", True)

    def u_command(self) -> Any:
        net = self.net
        if self.have_command("undefine-path", True):
            if self.empty():
                self.error("The command undefine-path needs a relation.")
            rel = self.get_form()
            if not net.is_r(_name(rel)):
                self.error(f"The command undefine-path was called on {_name(rel)}, which is not a "
                           "relation.")
            self.have_command(".")
            return ["undefine-path", rel]
        if self.have_command("unlabeled"):
            return self.return_forms(lambda: setattr(net, "complete_description", "unlabeled"))
        return self._trace_command("untrace", False)

    def _trace_command(self, word: str, on: bool) -> Any:
        net = self.net
        if not self.have_command(word, True):
            return None
        if self.inp == "" or self.have_command("."):
            return self.return_forms(lambda: setattr(net, "trace_translation", on))
        forms = []
        while True:
            f = self.snepslog_symbol()
            if f is None:
                break
            n = _name(f).lower()
            un = "" if on else "Un"
            if n == "inference":
                forms.append(lambda on=on: setattr(net, "infertrace", "surface" if on else None))
                forms.append(_writer(net, f"{un}{'t' if not on else 'T'}racing inference."))
            elif n == "acting":
                forms.append(lambda on=on: setattr(net, "plantrace_mode", "surface" if on else None))
                forms.append(_writer(net, f"{un}{'t' if not on else 'T'}racing acting."))
            elif n == "translation":
                forms.append(lambda on=on: setattr(net, "trace_translation", on))
                forms.append(_writer(net, f"{un}{'t' if not on else 'T'}racing translation to SNePSUL."))
            elif n == "parsing":
                forms.append(lambda on=on: setattr(net, "trace_parsing", on))
                forms.append(_writer(net, f"{un}{'t' if not on else 'T'}racing SNePSLOG parsing."))
            else:
                forms.append(_writer(net, f"{_name(f)} is not fbound."))
        self.have_command(".")
        return self.return_forms(*forms)

    def e_command(self) -> Any:
        if self.have_command("exit"):
            raise SnepslogEnd()
        if self.have_command("expert"):
            return self.return_forms(lambda: setattr(self.net, "complete_description", "expert"))
        return None

    def n_command(self) -> Any:
        if self.have_command("normal"):
            return self.return_forms(lambda: setattr(self.net, "complete_description", "normal"))
        return None

    def c_command(self) -> Any:
        net = self.net
        if self.have_command("clear-infer"):
            return ["clear-infer"]
        if self.have_command("clearkb"):
            def clearkb() -> None:
                from ..io.streams import NullOutputStream
                with net.let(outunit=NullOutputStream()):
                    net.resetnet(False)
            return self.return_forms(clearkb, _writer(net, "Knowledge Base Cleared"))
        if self.have_command("copyright"):
            return ["copyright"]
        return None

    def caret_command(self) -> Any:
        """``^^`` reads Python until a line ``^^``; ``^ code`` runs the rest of
        the input as Python and prints the value of an expression."""
        net = self.net
        if len(self.inp) > 1 and self.inp[1] == "^":
            rest = self.inp[2:].strip()
            self.inp = ""
            if rest:
                return self.return_forms(lambda: net.python.run(rest), net.python.loop)
            return self.return_forms(net.python.loop)
        source = self.inp[1:].strip()
        self.inp = ""
        return self.return_forms(lambda: net.python.run(source))

    def percent_command(self) -> Any:
        self.pop_input(1)
        return self.get_form(snepsul=True)

    # ------------------------------------------------------------------
    # wff commands
    def wff_name_command(self) -> Any:
        node = self.wff_name()
        if node is None:
            return None
        net = self.net
        if len(self.inp) >= 2 and self.inp[:2] == "??":
            self.pop_input(2)
            if net.isassert(net.node(node)):
                return node
            return self.return_forms()
        if len(self.inp) < 1:
            self.error(f"Invalid punction after wffName at: {_s(self.inp)}")
        c = self.inp[0]
        if c == ".":
            self.pop_input(1)
            return ["!", node]
        if c == "!":
            self.pop_input(1)
            return lambda: list(net.add_star(net.nseval(["!", node])))
        if c == "?":
            self.pop_input(1)
            limits = self.check_deduce_limits([None])
            lim = limits[1] if len(limits) > 1 else None
            n = net.node(node)
            return lambda: list(net.deduce_star(lim, (n,)))
        return None

    def wff_command(self) -> Any:
        wff = self.wff()
        if wff is None:
            return None
        punct = self.terminal_punctuation()
        if punct is None:
            self.error(f"Wff {_show(wff)} not followed by terminal punctuation at {_s(self.inp)}")
        if not isinstance(wff, list) or _is(wff[0], "?"):
            self.error(f"Atomic, top-level wff, {_show(wff)}, is not allowed")
        args = wff[1:]
        if punct == ".":
            if (self.net.in_mode3() and any(_is(x, "do") for x in args)
                    and any(_is(x, n) for x in args for n in ("when", "whenever", "if"))):
                return ["adopt"] + args
            return ["assert"] + args
        if punct == "!":
            return ["add"] + args
        if punct == "?":
            return self.check_deduce_limits(self.fix_qvars_for_deduce(["deduce"] + args))
        if punct == "??":
            return ["findassert"] + _subst_build_find(args)
        self.error(f"Unrecognized punctuation {punct} after wff {_show(wff)}")

    def check_deduce_limits(self, form: list) -> list:
        if self.first_charp("("):
            limits = self.get_form()
            if isinstance(limits, list) and len(limits) == 1 and isinstance(limits[0], int):
                return [form[0], limits[0]] + form[1:]
            if (isinstance(limits, list) and len(limits) == 2
                    and all(isinstance(x, int) for x in limits)):
                return [form[0], limits] + form[1:]
            self.error(f"Invalid list following `?': {_show(limits)}")
        return form

    def fix_qvars_for_deduce(self, form: list) -> list:
        seen: list = []

        def fixns(ns: Any) -> Any:
            if not isinstance(ns, list):
                return ns
            if len(ns) == 2 and _is(ns[0], "?"):
                v = ns[1]
                if any(v == x for x in seen):
                    return [STAR, v]
                seen.insert(0, v)
                return [DOLLAR, v]
            if ns and _is(ns[0], "build"):
                return [BUILD] + fixbuildargs(ns[1:])
            return [fixns(x) for x in ns]

        def fixbuildargs(f: list) -> list:
            out = []
            for k in range(0, len(f), 2):
                out.append(f[k])
                out.append(fixns(f[k + 1]) if k + 1 < len(f) else None)
            return out
        return [form[0]] + fixbuildargs(form[1:])

    def terminal_punctuation(self) -> Optional[str]:
        if self.empty():
            return None
        c = self.inp[0]
        if c == ".":
            self.pop_input(1)
            return "."
        if c == "!":
            self.pop_input(1)
            return "!"
        if c == "?":
            if len(self.inp) > 1 and self.inp[1] == "?":
                self.pop_input(2)
                return "??"
            self.pop_input(1)
            return "?"
        return None

    # ------------------------------------------------------------------
    # wffs and terms
    def wff(self) -> Any:
        if self.first_charp("{"):
            return self.entailment()
        first = self.prefixed_term()
        if first is None:
            return None
        conn = self.infix_op()
        if conn:
            return self.infixed_term(first, conn)
        op = self.have_entailment_op()
        if op is not None:
            return self.entailment_cq(first, op)
        return first

    def infix_op(self) -> Optional[str]:
        n = len(self.inp)
        if n > 3 and self.inp[:3].lower() == "and":
            self.pop_input(3)
            return "and"
        if n > 3 and self.inp[:3].lower() == "<=>":
            self.pop_input(3)
            return "<=>"
        if n > 2 and self.inp[:2].lower() == "or":
            self.pop_input(2)
            return "or"
        return None

    def infixed_term(self, first: Any, conn: str) -> list:
        wffs = [first]
        n = len(conn)
        while True:
            wffs.append(self.prefixed_term())
            if not len(self.inp) > n:
                break
            if self.inp[0] in TERMINAL_PUNCTUATION:
                break
            if self.inp[:n].lower() == conn:
                self.pop_input(n)
            else:
                self.error(f"Bad connective in {conn}ed sequence at: {_s(self.inp)}")
        k = len(wffs)
        if conn == "<=>":
            return [BUILD, "thresh", 1, "arg", wffs]
        return [BUILD, "min", 1 if conn == "or" else k, "max", k, "arg", wffs]

    def entailment(self) -> Any:
        ant = self.term_set()
        if ant is not None:
            op = self.have_entailment_op()
            if op is not None:
                return self.entailment_cq(ant, op)
            self.error(f"Entailment {_show(ant)} missing entailment operator at: {_s(self.inp)}")
        return None

    def entailment_cq(self, ant: Any, op: Any) -> list:
        cq = self.term_set()
        if cq is None:
            self.error(f"Entailment {_show(ant)} {op} missing consequent at: {_s(self.inp)}")
        if op == "v=>":
            return [BUILD, "ant", ant, "cq", cq]
        if op == "&=>":
            return [BUILD, "&ant", ant, "cq", cq]
        if isinstance(op, int):
            return [BUILD, "thresh", op, "&ant", ant, "cq", cq]
        self.error(f"Unknown entailment operator: {op}")

    def have_entailment_op(self) -> Any:
        n = len(self.inp)
        if n >= 2 and self.inp[:2] == "=>":
            self.pop_input(2)
            return "v=>"
        if n >= 3 and self.inp[:3] == "v=>":
            self.pop_input(3)
            return "v=>"
        if n >= 3 and self.inp[:3] == "&=>":
            self.pop_input(3)
            return "&=>"
        if n >= 3 and self.inp[0].isdigit():
            k = self.inp.find("=")
            if k > 0 and self.inp[:k].isdigit() and self.inp[k:k + 2] == "=>":
                i = int(self.inp[:k])
                self.pop_input(k + 2)
                return i
        return None

    def prefixed_term(self) -> Any:
        if self.empty():
            return None
        c = self.inp[0]
        if c == "~":
            return self.negated_term()
        if c == "a":
            return self.andor_term() or self.all_term() or self.and_term() or self.atomic_term()
        if c == "i":
            return self.iff_term() or self.atomic_term()
        if c == "n":
            return self.nor_term() or self.nand_term() or self.nexists_term() or self.atomic_term()
        if c == "o":
            return self.or_term() or self.atomic_term()
        if c == "t":
            return self.thresh_term() or self.atomic_term()
        if c == "x":
            return self.xor_term() or self.atomic_term()
        return self.atomic_term()

    def _keyword_set(self, kw: str) -> bool:
        n = len(kw)
        return len(self.inp) > n and self.inp[:n].lower() == kw and self.inp[n] == "{"

    def nexists_term(self) -> Any:
        if not (len(self.inp) > 7 and self.inp[:7].lower() == "nexists" and self.inp[7] == "("):
            return None
        self.pop_input(7)
        if not self.first_charp("("):
            return self.replace_token("nexists")
        params = self.nexists_parameters()
        if not params:
            self.error(f"nexists must be followed by nexistsParameters at: {_s(self.inp)}")
        if not self.first_charp("("):
            return None
        self.pop_input(1)
        vars_ = self.symbol_sequence()
        if not vars_:
            self.error(f"nexists requires a list of variables at: {_s(self.inp)}")
        self.pop_input(1)
        if not self.first_charp("("):
            self.error(f"nexists must be followed by (wff(s) : wff(s)) at: {_s(self.inp)}")
        self.pop_input(1)
        ant = self.term_set()
        if ant is None:
            self.error(f"Missing termSet at: {_s(self.inp)}")
        if not self.first_charp(":"):
            self.error(f"Missing nexists : separator at: {_s(self.inp)}")
        self.pop_input(1)
        cq = self.term_set()
        if cq is None:
            self.error(f"Missing second sequence of nexists wffs at: {_s(self.inp)}")
        if not self.first_charp(")"):
            self.error(f"Missing close parenthesis at: {_s(self.inp)}")
        self.pop_input(1)
        return [BUILD, "emin", params[0], "emax", params[1], "etot", params[2],
                "pevb", [[DOLLAR, v] for v in vars_],
                "&ant", self.fix_ns_vars_for_all(ant, vars_),
                "cq", self.fix_ns_vars_for_all(cq, vars_)]

    def nexists_parameters(self) -> Optional[list]:
        if not self.first_charp("("):
            return None
        self.pop_input(1)
        params = [self.nexists_parameter()]
        for _ in range(2):
            if self.first_charp(","):
                self.pop_input(1)
            else:
                self.error(f"Incorrect nexists parameter punctuation at: {_s(self.inp)}")
            params.append(self.nexists_parameter())
        if self.first_charp(")"):
            self.pop_input(1)
        else:
            self.error(f"Missing close parenthesis after nexists parameters at: {_s(self.inp)}")
        if all(p is not None for p in params) or params[1] is None or (
                params[0] is None and params[2] is None):
            return params
        self.error(f"Illegal nexists parametes: {params}")

    def nexists_parameter(self) -> Optional[int]:
        if self.first_charp("_"):
            self.pop_input(1)
            return None
        p = self.get_form()
        if isinstance(p, int):
            return p
        self.error(f"nexists requires parameters (i, j, k) at: {_s(self.inp)}")

    def all_term(self) -> Any:
        if not (len(self.inp) >= 3 and self.inp[:3].lower() == "all"):
            return None
        self.pop_input(3)
        if not self.first_charp("("):
            return self.replace_token("all")
        self.pop_input(1)
        vars_ = self.symbol_sequence()
        if not vars_:
            self.error(f"all requires a list of variables at: {_s(self.inp)}")
        self.pop_input(1)
        if not self.first_charp("("):
            self.error(f"Universally quantified wff all{_show(vars_)} is missing a parenthesized "
                       f"wff at: {_s(self.inp)}.")
        self.pop_input(1)
        wff = self.wff()
        if wff is None:
            self.error(f"Universally quantified wff all{_show(vars_)}_____ is missing its scope "
                       f"at: {_s(self.inp)}.")
        if not self.first_charp(")"):
            self.error(f"Universally quantified wff all{_show(vars_)}({_show(wff)} is missing a "
                       f"close parenthesis at: {_s(self.inp)}.")
        if not isinstance(wff, list):
            self.error(f"Scope of all cannot be an atomic symbol {_show(wff)} before: {_s(self.inp)}.")
        self.pop_input(1)
        return [BUILD, "forall", [[DOLLAR, v] for v in vars_]] + \
            self.fix_vars_for_all(wff[1:], vars_)

    def fix_ns_vars_for_all(self, ns: Any, vars_: list) -> Any:
        if not isinstance(ns, list):
            return [STAR, ns] if isinstance(ns, str) and ns in vars_ else ns
        if _qlistp(ns) and ns[1] in vars_:
            return [STAR, ns[1]]
        if ns and (_is(ns[0], "*") or _is(ns[0], "$")):
            return ns
        if ns and self.net.is_com(ns[0]):
            return [ns[0]] + self.fix_vars_for_all(ns[1:], vars_)
        return [self.fix_ns_vars_for_all(f, vars_) for f in ns]

    def fix_vars_for_all(self, form: list, vars_: list) -> list:
        out = []
        for k in range(0, len(form), 2):
            r = form[k]
            ns = form[k + 1] if k + 1 < len(form) else None
            out.append(r)
            out.append(ns if _is(r, "forall") else self.fix_ns_vars_for_all(ns, vars_))
        return out

    def and_term(self) -> Any:
        if not self._keyword_set("and"):
            return None
        self.pop_input(3)
        args = self.term_set()
        if args:
            return [BUILD, "min", len(args), "max", len(args), "arg", args]
        self.error(f"and must take a set of at least 1 argument at: {_s(self.inp)}")

    def iff_term(self) -> Any:
        if not self._keyword_set("iff"):
            return None
        self.pop_input(3)
        args = self.term_set()
        if args:
            return [BUILD, "thresh", 1, "arg", args]
        self.error(f"iff must take a set of at least 1 argument at: {_s(self.inp)}")

    def nor_term(self) -> Any:
        if not self._keyword_set("nor"):
            return None
        self.pop_input(3)
        args = self.term_set()
        if args:
            return [BUILD, "min", 0, "max", 0, "arg", args]
        self.error(f"nor must take a set of at least 1 argument at: {_s(self.inp)}")

    def nand_term(self) -> Any:
        if not self._keyword_set("nand"):
            return None
        self.pop_input(4)
        args = self.term_set()
        if args:
            return [BUILD, "min", 0, "max", len(args) - 1, "arg", args]
        self.error(f"nand must take a set of at least 1 argument at: {_s(self.inp)}")

    def or_term(self) -> Any:
        if not self._keyword_set("or"):
            return None
        self.pop_input(2)
        args = self.term_set()
        if args:
            return [BUILD, "min", 1, "max", len(args), "arg", args]
        self.error(f"or must take a set of at least 1 argument at: {_s(self.inp)}")

    def xor_term(self) -> Any:
        if not self._keyword_set("xor"):
            return None
        self.pop_input(3)
        args = self.term_set()
        if args:
            return [BUILD, "min", 1, "max", 1, "arg", args]
        self.error(f"xor must take a set of at least 1 argument at: {_s(self.inp)}")

    def andor_term(self) -> Any:
        if not (len(self.inp) > 5 and self.inp[:5].lower() == "andor" and self.inp[5] == "("):
            return None
        self.pop_input(5)
        if not self.first_charp("("):
            return self.replace_token("andor")
        params = self.nparams("andor")
        if not params:
            self.error(f"andor must be followed by a list of 2 parameters at: {_s(self.inp)}")
        args = self.term_set()
        if args:
            return [BUILD, "min", params[0], "max", params[1], "arg", args]
        self.error(f"andor{params} must take a set of at least {max(params[1], 1)} arguments at: "
                   f"{_s(self.inp)}")

    def thresh_term(self) -> Any:
        if not (len(self.inp) > 6 and self.inp[:6].lower() == "thresh" and self.inp[6] == "("):
            return None
        self.pop_input(6)
        if not self.first_charp("("):
            return self.replace_token("thresh")
        params = self.nparams("thresh")
        if not params:
            self.error(f"thresh must be followed by a list of 1 or 2 parameters at: {_s(self.inp)}")
        args = self.term_set()
        if args:
            return [BUILD, "thresh", params[0], "threshmax",
                    params[1] if len(params) > 1 else None, "arg", args]
        self.error(f"thresh{params} must take a set of arguments at: {_s(self.inp)}")

    def negated_term(self) -> Any:
        if self.first_charp("~"):
            self.pop_input(1)
            term = self.atomic_term()
            if term is not None:
                return [BUILD, "min", 0, "max", 0, "arg", term]
            self.error(f"Negation operator not followed by a term at: {_s(self.inp)}")
        return None

    def atomic_term(self) -> Any:
        if self.first_charp("("):
            self.pop_input(1)
            wff = self.wff()
            if wff is not None:
                if self.first_charp(")"):
                    self.pop_input(1)
                    return wff
                self.error(f"Wff ({_show(wff)} missing close parenthesis at: {_s(self.inp)}")
            self.error(f"Unrecognized wff at: {_s(self.inp)}")
        name = self.wff_name()
        if name is not None:
            return name
        fsym = self.qvar() or self.snepslog_symbol()
        if fsym is None:
            return None
        if self.first_charp("("):
            self.pop_input(1)
            trmsqce = self.term_set_sequence()
            if self.first_charp(")"):
                self.pop_input(1)
                expr = self.net.make_relation(BUILD, fsym, trmsqce or [])
                if len(expr) > 1:
                    if self.net.in_mode3() and isinstance(fsym, str) and \
                            fsym.lower() in ("withsome", "withall"):
                        return self.withsome_all_term(fsym, expr)
                    return expr
                self.error(f"No caseframe has been defined for {_show(fsym)}.")
            self.error(f"Bad punctuation at {_s(self.inp)}")
        return fsym

    def withsome_all_term(self, fsym: Any, expr: list) -> list:
        if len(expr) < 9:
            self.error(f"Insufficient number of arguments for {_name(fsym)}: {_show(expr)} just "
                       f"before: {_s(self.inp)}")
        vars_ = _varlist(expr[4])
        return [BUILD, "action", fsym, "vars", [[DOLLAR, v] for v in vars_]] + \
            self.fix_vars_for_all(expr[5:], vars_)

    def term_set_sequence(self) -> Optional[list]:
        first = self.term_set()
        if first is None:
            return None
        out = [first]
        while not (self.inp and self.inp[0] in TERMINAL_PUNCTUATION) and self.inp:
            if self.first_charp(","):
                self.pop_input(1)
            else:
                self.error(f"Bad punctuation in termSequence at {_s(self.inp)}")
            out.append(self.term_set())
        return out

    def replace_token(self, token: str) -> None:
        self.inp = token + self.inp
        return None

    def term_set(self) -> Any:
        if self.first_charp("{"):
            self.pop_input(1)
            seq = self.term_sequence()
            if seq:
                if self.first_charp("}"):
                    self.pop_input(1)
                    return seq
                self.error(f"Bad punctuation at {_s(self.inp)}")
            self.error(f"Empty termSequence just before {_s(self.inp)}")
        return self.prefixed_term()

    def nparams(self, operator: str) -> Optional[list]:
        if not self.first_charp("("):
            return None
        k = self.inp.find(")")
        if k < 0:
            self.error(f"List begins but doesn't end at : {_s(self.inp)}")
        text = self.inp[:k + 1]
        try:
            lst, _ = read_from_string(text.replace(",", " "))
        except ReaderError:
            lst = None
        lst = lst or []
        ok = all(isinstance(x, int) and not isinstance(x, bool) for x in lst) and \
            all(a <= b for a, b in zip([0] + lst, lst))
        if (operator == "andor" and len(lst) == 2 and ok) or (
                operator == "thresh" and 1 <= len(lst) <= 2 and ok):
            self.pop_input(k + 1)
            return lst
        self.error(f"Improper list of numerical parameters: {_s(text)}")

    def term_sequence(self) -> Optional[list]:
        first = self.prefixed_term()
        if first is None:
            return None
        out = [first]
        while self.inp and self.inp[0] not in TERMINAL_PUNCTUATION:
            if self.first_charp(","):
                self.pop_input(1)
            else:
                self.error(f"Bad punctuation in termSequence at {_s(self.inp)}")
            out.append(self.prefixed_term())
        return out

    def symbol_sequence(self) -> Optional[list]:
        first = self.snepslog_symbol()
        if first is None:
            return None
        out = [first]
        while self.inp and self.inp[0] not in TERMINAL_PUNCTUATION:
            if self.first_charp(","):
                self.pop_input(1)
            else:
                self.error(f"Bad punctuation in symbolSequence at {_s(self.inp)}")
            out.append(self.snepslog_symbol())
        return out

    def required_wff_arg(self, command: str) -> list:
        wff = self.wff()
        if wff is not None:
            self.terminal_punctuation()
            return wff if isinstance(wff, list) else [None, wff]
        self.error(f"The command {command} requires a wff as an argument at {_s(self.inp)}")


class SnepslogEnd(Exception):
    """The SNePSLOG ``exit`` command: leave the SNePSLOG top level."""


def _writer(net: Any, msg: str) -> Callable[[], None]:
    return lambda: net.write(msg)


def _is(x: Any, name: str) -> bool:
    return type(x) is str and not x.startswith(":") and x.lower() == name


def _name(x: Any) -> str:
    return str(x)


def _qlistp(form: Any) -> bool:
    return (isinstance(form, list) and len(form) == 2 and _is(form[0], "?")
            and not isinstance(form[1], list))


def _varlist(spec: Any) -> list:
    if not isinstance(spec, list):
        return [spec]
    if _qlistp(spec):
        return spec[1:]
    out: list = []
    for x in spec:
        out.extend(_varlist(x))
    return out


def _subst_build_find(x: Any) -> Any:
    if isinstance(x, list):
        return ["find" if _is(e, "build") else _subst_build_find(e) for e in x]
    return x


def _s(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _show(x: Any) -> str:
    return flat_text(x, True)
