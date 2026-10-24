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
"""Evaluation of SNePSUL, the SNePS User Language (SNePS 2.8 ``sneps/fns``).

SNePSUL expressions are read by :mod:`sneps.snepsul.reader` into Python
lists, names and numbers, and evaluated here.  Every command is legal in a
set of *environments*: ``top`` (the top level), ``ns`` (node-set
positions), ``bns`` (inside ``build``), ``fns`` (inside ``find``), ``rs``
(relation positions) and ``rearrange`` (infix use).  A command is a Python
function called with the network and its argument list; it returns a
:class:`Result` (its value and the context it used) or just a value.

Besides SNePSUL forms, the top level evaluates Python callables: SNePSLOG
translates its own commands into them, and SNePS uses them for the commands
it runs internally (belief revision may re-run the last command).
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterable, NamedTuple, Optional

from ..core.context import Context
from ..core.network import SNePSError
from ..core.node import Node, number_name
from ..core.nodeset import ns_compl, ns_make, ns_union
from ..core.printing import flat_text, pretty_text
from ..io.streams import InputStream, NullOutputStream, OutputStream
from .reader import EOF, PythonCode, ReaderError, SnepsulReader

ENVIRONMENTS = ("top", "rs", "bns", "tbns", "fns", "ns", "rearrange")


class Result(NamedTuple):
    """The value of a SNePSUL command and the context it was evaluated in."""

    value: Any = None
    context: Any = None


def as_result(x: Any) -> Result:
    return x if isinstance(x, Result) else Result(x, None)


class Command:
    __slots__ = ("name", "fn", "envs", "eval_args", "doc")

    def __init__(self, name: str, fn: Callable, envs: Iterable[str], eval_args: bool = False,
                 doc: Optional[str] = None):
        self.name = name
        self.fn = fn
        self.envs = frozenset(envs)
        self.eval_args = eval_args
        self.doc = doc


COMMANDS: dict[str, Command] = {}


def environments(envs: Any, commands: dict) -> frozenset:
    """ENVS as a set of environment names: a sequence of names, ``"all"``,
    or the name of a command whose environments are copied."""
    if envs == "all":
        return frozenset(ENVIRONMENTS)
    if isinstance(envs, str):
        other = commands.get(envs)
        return other.envs if other is not None else frozenset(["top"])
    return frozenset("ns" if e == "ons" else e for e in envs)


def define_command(name: str, envs: Any = ("top",), eval_args: bool = False) -> Callable:
    """Decorator registering a built-in SNePSUL command.  Commands with
    EVAL_ARGS receive their arguments with quotes and ``^`` escapes evaluated."""
    def deco(fn: Callable) -> Callable:
        COMMANDS[name] = Command(name, fn, environments(envs, COMMANDS), eval_args, fn.__doc__)
        return fn
    return deco


def sym_name(x: Any) -> str:
    """The node or relation name that a SNePSUL datum designates."""
    if isinstance(x, str):
        return str(x)
    if isinstance(x, Node):
        return x.name
    if isinstance(x, bool):
        return "t" if x else "nil"
    if x is None:
        return "nil"
    if isinstance(x, (int, float)) or type(x).__name__ == "Fraction":
        return number_name(x)
    return flat_text(x)


def is_name(x: Any) -> bool:
    """X is a name (not a string literal or keyword)."""
    return type(x) is str and not x.startswith(":")


def _is(x: Any, name: str) -> bool:
    return is_name(x) and x.lower() == name


def _is_kw(x: Any, name: str) -> bool:
    return type(x) is str and x.lower() == ":" + name


#: Pause controls that pause before / after reading each demo input.
_PAUSE_BEFORE = ("b", "before", "pause", "t", "bv", "before-verbose")
_PAUSE_AFTER = ("a", "after", "av", "after-verbose")

#: Default for START-DEMO's PAUSE: copy the pause control of the current demo.
INHERIT_PAUSE = object()


class SnepsulMixin:
    """The SNePSUL evaluator and top level, mixed into :class:`~sneps.Network`."""

    def _init_snepsul(self) -> None:
        from ..host import PythonHost
        self.commands: dict[str, Command] = dict(COMMANDS)
        self.sneps_prompt = "* "
        self.show_timing = True
        self.fold_case: Optional[str] = None
        self._exit_flag = False
        self._input_stack: list = []
        self.demo_pause: Any = None
        self.sneps_directory: Optional[str] = None
        self.python = PythonHost(self)

    # ------------------------------------------------------------------
    # paths and file names
    def translate_path(self, path: Any) -> str:
        """Translate a SNePS logical pathname (``sneps:demo;x;y.sneps``)."""
        p = sym_name(path) if not isinstance(path, str) else str(path)
        if p.lower().startswith("sneps:"):
            parts = p[6:].split(";")
            root = self.sneps_directory or _default_sneps_directory()
            physical = os.path.join(root, *parts)
            if not os.path.exists(physical):
                # logical pathnames are case-insensitive and translate to
                # lower-case physical names
                lowered = os.path.join(root, *(x.lower() for x in parts))
                if os.path.exists(lowered):
                    return lowered
            return physical
        return os.path.expanduser(p)

    # ------------------------------------------------------------------
    # commands and environments
    def is_com(self, x: Any, env: Optional[str] = None) -> bool:
        if not is_name(x):
            return False
        cmd = self.commands.get(x.lower())
        if cmd is None:
            return False
        return env is None or env in cmd.envs

    def call_command(self, form: list) -> Result:
        """Run the command FORM (whose head names a command)."""
        cmd = self.commands[form[0].lower()]
        args = list(form[1:])
        if cmd.eval_args:
            args = [self.eval_arg(a) for a in args]
        return as_result(cmd.fn(self, args))

    def eval_arg(self, x: Any) -> Any:
        """The value of an argument of a command that evaluates its arguments:
        ``(quote x)`` is X and ``^`` escapes are evaluated in Python."""
        if isinstance(x, list) and len(x) == 2:
            if _is(x[0], "quote"):
                return x[1]
            if _is(x[0], "^") and isinstance(x[1], PythonCode):
                return self.python.evaluate(x[1].source)
        return x

    def _python_nodes(self, form: list, build: bool) -> tuple:
        """The node set designated by the value of the Python escape FORM."""
        value = self.python.evaluate(form[1].source) if isinstance(form[1], PythonCode) else None
        return self._value_ns(value, build)

    def _value_ns(self, value: Any, build: bool) -> tuple:
        if value is None:
            return ()
        if isinstance(value, (Node, Context)):
            return (value,)
        if isinstance(value, (list, tuple, set, frozenset)):
            out: list = []
            for v in value:
                for n in self._value_ns(v, build):
                    if not any(n is m for m in out):
                        out.append(n)
            return tuple(out)
        name = sym_name(value)
        n = self.node(name)
        if n is None and build:
            n = self.newpbase(name)
        if n is None:
            raise SNePSError(f" Unknown node: {name}", "nodeset-evaluator", "nseval-atom")
        return (n,)

    # ------------------------------------------------------------------
    # evaluation of SNePSUL expressions
    def topsneval(self, form: Any) -> Result:
        """Evaluate a top-level SNePSUL form (or a Python callable)."""
        self.set_sv("command", form)
        try:
            if callable(form) and not isinstance(form, (str, list, Node)):
                res = form()
                res = res if isinstance(res, Result) else Result(res, self.value_sv("defaultct"))
                self.set_sv("lastvalue", res.value)
                return res
            if form is None or (isinstance(form, list) and not form):
                self.set_sv("lastvalue", ())
                return Result((), None)
            if isinstance(form, list):
                return self._topsneval_seq(form)
            return self._topsneval_atom(form)
        except SNePSError as e:
            self._report_sneps_error(e)
            return Result(None, None)

    def run_silently(self, thunk: Callable[[], Any]) -> Any:
        """Run THUNK as a top-level command with its output suppressed."""
        with self.let(outunit=NullOutputStream()):
            return self.topsneval(thunk)

    def _report_sneps_error(self, e: SNePSError) -> None:
        self.fresh_line()
        self.write(f"SNePS ERROR: {e.msg}\n")
        if e.module is not None or e.fn is not None:
            self.write(f"Occurred in module {sym_name(e.module) if e.module is not None else 'nil'} "
                       f"in function {sym_name(e.fn) if e.fn is not None else 'nil'}\n")
        self.set_sv("errorcommand", self.value_sv("lastcommand"))

    def _topsneval_atom(self, form: Any) -> Result:
        if self.is_com(form, "rearrange"):
            if _is(form, "!"):
                cmd = [form, self.value_sv("lastvalue")]
            else:
                cmd = [form, self.value_sv("lastvalue"), self.sneps_read()]
            v = self.nseval(cmd)
            self.set_sv("lastvalue", v)
            return Result(v, None)
        if _is(form, "^^"):
            rest, _ = self.inunit.read_line() if self.inunit is not None else ("", True)
            if rest and rest.strip():
                self.python.run(rest)
            self.python.loop()
            return Result(None, None)
        if isinstance(form, (int, float)) and not isinstance(form, bool):
            return self._topsneval_atom(number_name(form))
        if isinstance(form, Node) or (isinstance(form, str) and self.snepsul_node(str(form))):
            n = form if isinstance(form, Node) else self.snepsul_node(str(form))
            self.set_sv("lastvalue", (n,))
            return Result((n,), None)
        if form is None:
            return Result(None, None)
        raise SNePSError(f"Invalid top SNePSUL form: {flat_text(form, True)}",
                         "top-evaluator", "top-sneval")

    def _topsneval_seq(self, form: list) -> Result:
        head = form[0]
        if self.is_com(head, "top"):
            res = self.call_command(form)
            self.set_sv("lastvalue", res.value)
            return res
        if all(self._is_node_access(x) for x in form):
            ns = ns_make(self.node(sym_name(x)) for x in form)
            self.set_sv("lastvalue", ns)
            return Result(ns, None)
        raise SNePSError(f"Invalid top SNePSUL form: {flat_text(form, True)}",
                         "top-evaluator", "topsneval")

    def _is_node_access(self, x: Any) -> bool:
        if isinstance(x, Node):
            return True
        if isinstance(x, (str, int, float)) and not isinstance(x, bool):
            return self.node(sym_name(x)) is not None
        return False

    def nseval(self, exp: Any) -> tuple:
        """Evaluate a SNePSUL node-set expression."""
        if exp is None:
            return ()
        if isinstance(exp, tuple):
            return exp
        if isinstance(exp, Context):
            return (exp,)
        if not isinstance(exp, list):
            return self._nseval_atom(exp)
        if not exp:
            return ()
        head = exp[0]
        if _is(head, "^"):
            return self._python_nodes(exp, build=False)
        if self.is_com(head, "ns"):
            res = self.call_command(exp).value
        elif len(exp) > 1 and _is(exp[1], "!"):
            return self.nseval([["!", exp[0]]] + exp[2:])
        elif len(exp) > 1 and self.is_com(exp[1], "rearrange"):
            if len(exp) > 2:
                return self.nseval([[exp[1], exp[0], exp[2]]] + exp[3:])
            raise SNePSError(f"Infix operator missing second operand:: {flat_text(exp[1:])}",
                             "evaluation of node description", "nseval")
        else:
            res = ()
            for e in exp:
                res = ns_union(res, self.nseval(e))
        return _as_ns(res)

    def _nseval_atom(self, exp: Any) -> tuple:
        if isinstance(exp, (Node, Context)):
            return (exp,)
        name = sym_name(exp)
        n = self.snepsul_node(name)
        if n is not None:
            return (n,)
        raise SNePSError(f" Unknown node: {name}", "nodeset-evaluator", "nseval-atom")

    def rseval(self, exp: Any) -> Any:
        """Evaluate a relation-set expression; returns a relation name or a list."""
        if exp is None:
            return None
        if not isinstance(exp, list):
            name = sym_name(exp)
            if self.is_r(name):
                return name
            raise SNePSError(f"{name} is not a relation", "relationset-evaluator", "rseval")
        if exp and self.is_com(exp[0], "rs"):
            return self.call_command(exp).value
        result: list = []
        for e in exp:
            r = self.rseval(e)
            for x in (r if isinstance(r, list) else [r] if r is not None else []):
                if x not in result:
                    result.append(x)
        if not result:
            return None
        return result[0] if len(result) == 1 else result

    def buildeval(self, nsform: Any, buildperm: bool = True) -> tuple:
        if nsform is None:
            return ()
        if isinstance(nsform, tuple):
            return nsform
        if not isinstance(nsform, list):
            if isinstance(nsform, Node):
                return (nsform,)
            name = sym_name(nsform)
            return (self.node(name) or self.newpbase(name),)
        if not nsform:
            return ()
        head = nsform[0]
        if _is(head, "^"):
            return self._python_nodes(nsform, build=True)
        if self.is_com(head):
            if self.is_com(head, "bns" if buildperm else "tbns"):
                res = self.call_command(nsform).value
                if not isinstance(res, (list, tuple)) or isinstance(res, Context):
                    if res is None:
                        return ()
                    return self.buildeval(res, True)
                return _as_ns(res)
            raise SNePSError(f"illegal command: {flat_text(head, True)}",
                             "build" if buildperm else "tbuild", "buildeval")
        ns: tuple = ()
        for f in nsform:
            ns = ns_union(self.buildeval(f, buildperm), ns)
        return ns

    def _nodesetform_snd(self, snd: list, k: int) -> Any:
        """The node-set form at SND[K], absorbing infix ``!`` and rearrange
        operators (SND is modified in place)."""
        while True:
            if k + 1 < len(snd) and _is(snd[k + 1], "!"):
                snd[k:k + 2] = [["!", snd[k]]]
            elif k + 1 < len(snd) and self.is_com(snd[k + 1], "rearrange"):
                if k + 2 < len(snd):
                    snd[k:k + 3] = [[snd[k + 1], snd[k], snd[k + 2]]]
                else:
                    raise SNePSError(f"Infix operator missing second operand: "
                                     f"{flat_text(snd[k + 1:])}",
                                     "Evaluation of node description", "nodesetform.snd")
            else:
                return snd[k]

    def evalsnd(self, snd: list, buildperm: bool = True) -> list:
        """Evaluate a build node description into a cable set."""
        from ..core.build import cs_insert
        if not snd:
            raise SNePSError("Attempted (t)build with no arguments",
                             "build" if buildperm else "tbuild", "evalsnd")
        snd = list(snd)
        cs: list = []
        k = 0
        while k < len(snd):
            rel = self.rseval(snd[k])
            if rel is None:
                raise SNePSError("Missing relation", "build" if buildperm else "tbuild", "evalsnd1")
            if isinstance(rel, list):
                raise SNePSError("error -- build cannot take a relation path",
                                 "build" if buildperm else "tbuild", "evalsnd1")
            if self.isup_r(rel):
                raise SNePSError(f"ascending relation is illegal in build: {rel}",
                                 "build" if buildperm else "tbuild", "evalsnd1")
            nsf = self._nodesetform_snd(snd, k + 1) if k + 1 < len(snd) else None
            ns = self.buildeval(nsf, buildperm)
            if ns:
                cs = cs_insert(cs, rel, ns)
            k += 2
        return cs

    # ------------------------------------------------------------------
    # context descriptions
    @staticmethod
    def iscontext_given(sd: list) -> Optional[list]:
        for k, x in enumerate(sd):
            if _is_kw(x, "context"):
                return sd[k + 1:] or None
        return None

    @staticmethod
    def getsndescr(sd: list) -> list:
        for k, x in enumerate(sd):
            if _is_kw(x, "context"):
                return sd[:k]
        return list(sd)

    def processcontextdescr(self, sd: list) -> Any:
        given = self.iscontext_given(sd)
        if not given:
            return self.crntcontext(None)
        if _is(given[0], "all-hyps"):
            return self.crntcontext(["all-hyps"])
        if len(given) == 1 and isinstance(given[0], str):
            return self.crntcontext([sym_name(given[0])])
        if len(given) == 2 and isinstance(given[1], str):
            return self.crntcontext([self.nseval(given[0]), sym_name(given[1])])
        raise SNePSError(f"Error in context description {flat_text(given)}",
                         "context", "crntcontext")

    def context_arg(self, x: Any) -> Any:
        """A context-name argument as used by the context commands."""
        if x is None:
            return None
        return sym_name(x)

    # ------------------------------------------------------------------
    # find
    def to_path(self, x: Any) -> Any:
        """A path expression as nested lists of relation names."""
        if isinstance(x, list):
            return [self.to_path(e) for e in x]
        return sym_name(x)

    def checkpath_form(self, x: Any) -> list:
        return self.checkpath(self.to_path(x))

    def fevalsnd(self, snd: list) -> tuple:
        snd = list(snd)
        consts: list = []
        qvars: list = []
        k = 0
        while k < len(snd):
            path = self.checkpath_form(snd[k])
            nsf = self._nodesetform_snd(snd, k + 1) if k + 1 < len(snd) else None
            if isinstance(nsf, list) and len(nsf) == 2 and _is(nsf[0], "?"):
                qvar = sym_name(nsf[1])
                if not self.is_sv(qvar):
                    self.new_sv(qvar)
                qvars.insert(0, (path, qvar))
            else:
                consts.insert(0, (path, self.findeval(nsf)))
            k += 2
        return consts, qvars

    def findeval(self, exp: Any) -> list:
        """Evaluate a node-set form inside ``find``; returns a node-bind set."""
        from ..core.build import ns_to_nbs
        if exp is None:
            return []
        if isinstance(exp, tuple):
            return ns_to_nbs(exp)
        if not isinstance(exp, list):
            return ns_to_nbs(self._findeval_atom(exp))
        if not exp:
            return []
        if _is(exp[0], "^"):
            return ns_to_nbs(self._python_nodes(exp, build=False))
        if self.is_com(exp[0], "fns"):
            res = self._insidefind(exp[1:]) if _is(exp[0], "find") else self.call_command(exp).value
            if res is None:
                return []
            if not isinstance(res, (list, tuple)):
                return self.findeval(res)
            if isinstance(res, list) and res and isinstance(res[0], tuple):
                return res
            return ns_to_nbs(_as_ns(res))
        result: tuple = ()
        for e in exp:
            if isinstance(e, list):
                raise SNePSError(" illegal snepsul expression ", "find", "findeval-map")
            result = ns_union(result, self._findeval_atom(e))
        return ns_to_nbs(result)

    def _findeval_atom(self, a: Any) -> tuple:
        if isinstance(a, Node):
            return (a,)
        n = self.node(sym_name(a))
        return (n,) if n is not None else ()

    def _insidefind(self, snd: list) -> list:
        ct = self.processcontextdescr(snd)
        with self.let(crntct=ct):
            consts, qvars = self.fevalsnd(self.getsndescr(snd))
            return self.find_nbs(consts, qvars)

    def find_command(self, snd: list, filt: Optional[Callable[[Node], bool]] = None) -> Result:
        ct = self.processcontextdescr(snd)
        with self.let(crntct=ct):
            consts, qvars = self.fevalsnd(self.getsndescr(snd))
            nbs = self.find_nbs(consts, qvars, filt)
            result = self.in_context_ns(self.nbs_to_ns(nbs), self.iscontext_given(snd))
        return Result(tuple(result), ct)

    # ------------------------------------------------------------------
    # the SNePS top level (sneps-loop)
    def snepsul_reader(self, stream: Optional[InputStream] = None) -> SnepsulReader:
        return SnepsulReader(stream if stream is not None else self.inunit, self.fold_case)

    def sneps_read(self) -> Any:
        """Read one SNePSUL form from the current input (EOF at the end)."""
        while True:
            if self.inunit is None:
                return EOF
            if self._input_stack and self.inunit.at_eof():
                self._end_demo()
                return ["dump"]
            in_demo = bool(self._input_stack)
            if in_demo and self.demo_pause_point("before") == "exit":
                return ["dump"]
            try:
                obj = self.snepsul_reader().read()
            except ReaderError as e:
                self.fresh_line()
                self.write(f"Error while reading: {e}\n")
                continue
            if obj is EOF and self._input_stack:
                self._end_demo()
                return ["dump"]
            if in_demo:
                status = self.demo_control(obj)
                if status == "done":
                    continue
                if status == "exit":
                    return ["dump"]
                if self.demo_pause_point("after") == "exit":
                    return ["dump"]
            return obj

    def sneps(self, inunit: Optional[InputStream] = None, outunit: Optional[OutputStream] = None,
              banner: bool = True) -> None:
        """Run the SNePS read-eval-print loop (until ``(exit)`` or the end of
        the input)."""
        import sys
        old = (self.inunit, self.outunit)
        if inunit is not None:
            self.inunit = inunit
        elif self.inunit is None:
            self.inunit = InputStream.from_textio(sys.stdin)
        if outunit is not None:
            self.outunit = outunit
        try:
            if banner:
                self._sneps_banner()
            self.sneps_loop()
        finally:
            self.inunit, self.outunit = old

    def _sneps_banner(self) -> None:
        from .. import __version__
        self.write(f"\n\n   Welcome to PySNePS {__version__} (SNePS 2.8 in Python)\n\n")
        t = time.localtime()
        self.write(f"   {t.tm_mon}/{t.tm_mday}/{t.tm_year} {t.tm_hour}:{t.tm_min:02d}:{t.tm_sec:02d}\n\n")

    def sneps_loop(self) -> None:
        self._exit_flag = False
        while True:
            self.write(self.sneps_prompt)
            form = self.sneps_read()
            if form is EOF:
                self.write("\n")
                return
            t0 = time.process_time()
            try:
                res = self.topsneval(form)
            except ReaderError as e:
                self.fresh_line()
                self.write(f"Error: {e}\n")
                res = Result()
            except Exception as e:  # keep the top level alive
                self.fresh_line()
                self.write(f"Error: {type(e).__name__}: {e}\n")
                res = Result()
            t1 = time.process_time()
            if self._exit_flag:
                return
            with self.let(crntct=res.context if res.context is not None else self.getcontext(())):
                self.fresh_line()
                self.write("\n")
                self.sneps_print(res.value)
            self.set_sv("lastcommand", form)
            self.sneps_timer(t0, t1)

    def sneps_print(self, s: Any) -> None:
        if s is None or (isinstance(s, (list, tuple)) and not s):
            return
        if not isinstance(s, (list, tuple)):
            s = [s]
        self.write(pretty_text(list(s), escape=False, column=self.outunit.column))

    def sneps_timer(self, t0: float, t1: float) -> None:
        self.fresh_line()
        if self.show_timing:
            self.write(f"\n CPU time : {t1 - t0:.2f} \n\n")
        else:
            self.write("\n")

    # ------------------------------------------------------------------
    # demos and input files
    def start_demo(self, file: str, pause: Any = INHERIT_PAUSE, output: Optional[OutputStream] = None,
                   use_batch_assert: bool = False) -> bool:
        if pause is INHERIT_PAUSE:
            # nested demos use the pause control of the enclosing demo
            pause = self.demo_pause
        path = self.translate_path(file)
        if not os.path.exists(path):
            self.fresh_line()
            self.write(f"\nThe file {file} does not exist. \n")
            return False
        out = output if output is not None else self.outunit
        stream = InputStream.from_file(path, echo=out)
        self._input_stack.append((self.inunit, self.outunit, self.demo_pause, path,
                                  use_batch_assert))
        if use_batch_assert:
            self.assert_later += 1
        self.inunit = stream
        self.outunit = out
        self.demo_pause = pause
        self.fresh_line()
        self.write(f"\nFile {os.path.abspath(path)} is now the source of input.\n")
        if pause:
            self.write("\n  The demo will pause between commands, at that time press"
                       "\n  RETURN to continue, or ? to see a list of available commands\n")
        return True

    def _end_demo(self) -> None:
        inunit, outunit, pause, path, batch = self._input_stack.pop()
        self.fresh_line()
        self.write(f"\nEnd of {os.path.abspath(path)} demonstration.")
        self.inunit, self.outunit, self.demo_pause = inunit, outunit, pause
        if batch:
            self.batch_assert(self.new_propositions)
            self.new_propositions = []
            self.assert_later -= 1

    # ------------------------------------------------------------------
    # demo control
    def _demo_interactive_io(self) -> tuple:
        """The streams that were current before the outermost demo started."""
        return self._input_stack[0][:2] if self._input_stack else (self.inunit, self.outunit)

    def demo_pause_point(self, when: str) -> Optional[str]:
        """Pause before or after a demo input, as the pause control says."""
        pause = self.demo_pause
        if not self._input_stack or not pause or pause == "n":
            return None
        if when == "before" and pause in _PAUSE_AFTER:
            return None
        if when == "after" and pause in _PAUSE_BEFORE:
            return None
        return self.demo_query(pause in ("bv", "before-verbose", "av", "after-verbose"))

    def demo_query(self, verbose: bool = False) -> Optional[str]:
        """Handle the user's answer at a pause point."""
        qin, qout = self._demo_interactive_io()
        while True:
            if verbose:
                qout.fresh_line()
                qout.write("--- pause ---")
            line, _ = qin.read_line() if qin is not None else (None, True)
            key = (line or "")[:1].lower()
            command = {"?": "dc-pause-help", "h": "dc-pause-help", "^": "dc-python",
                       "%": "dc-sneps", "s": "dc-sneps", ":": "dc-snepslog", "o": "dc-snepslog",
                       "c": "dc-no-pause", "p": "dc-read-pause"}.get(key)
            if key in ("q", "a"):
                qout.write("Do you really want to quit " + ("this demo" if key == "q" else "all demos")
                           + "? (yes or no) ")
                answer, _ = qin.read_line()
                if (answer or "").strip().lower() not in ("yes", "y"):
                    return None
                command = "dc-quit" if key == "q" else "dc-quit-all"
            if command is None:
                return None
            status = self.demo_control(command)
            if command != "dc-pause-help":
                return status
            # after the help message, ask again

    def demo_control(self, command: Any) -> Optional[str]:
        """Perform a demo control command; returns "done", "exit" or None."""
        head = command[0] if isinstance(command, list) and command else command
        if not is_name(head) or not head.lower().startswith("dc-"):
            return None
        name = head.lower()
        args = command[1:] if isinstance(command, list) else []
        qin, qout = self._demo_interactive_io()
        if name == "dc-pause-help":
            qout.write("\nThe following commands are available at pause points:"
                       "\n  h,?            Print this help message"
                       "\n  ^              Enter Python (type ^^ to continue)"
                       "\n  s,%            Enter SNePS toplevel loop"
                       "\n  o,:            Enter SNePSLOG"
                       "\n  c              Continue without pausing"
                       "\n  p              Set pause control"
                       "\n  q              Quit this demo"
                       "\n  a              Quit all demos"
                       "\n  any other key  Continue the demo"
                       "\n")
        elif name == "dc-python":
            with self.let(inunit=qin, outunit=qout):
                self.write("\nEnter Python. Type ^^ to continue\n")
                self.python.loop()
        elif name == "dc-sneps":
            with self.let(inunit=qin, outunit=qout):
                self.sneps_loop()
        elif name == "dc-snepslog":
            self.snepslog_repl(inunit=qin, outunit=qout)
        elif name == "dc-no-pause":
            self.demo_pause = None
        elif name == "dc-set-pause":
            self.demo_pause = sym_name(args[0]).lower() if args and args[0] is not None else None
        elif name == "dc-read-pause":
            while True:
                qout.write("\nEnter new pause control value (b,bv,a,av,n): ")
                line, _ = qin.read_line()
                if line is None:
                    break
                if line.strip().lower() in ("b", "bv", "a", "av", "n"):
                    self.demo_pause = line.strip().lower()
                    break
        elif name == "dc-quit":
            if self._input_stack:
                self._end_demo()
            return "exit"
        elif name == "dc-quit-all":
            while self._input_stack:
                self._end_demo()
            return "exit"
        else:
            return None
        return "done"

    def batch_assert(self, ns: list) -> None:
        from ..core.nodeset import ctcs_insert
        ns = list(reversed(ns))
        for n in ns:
            nct = self.buildcontext((n,))
            n.asupport = ctcs_insert("hyp", nct, n.asupport)
            self.sv_add("assertions", n)
        cur = self.get_context(self.crntct) if not isinstance(self.crntct, Context) else self.crntct
        self.name_ct(self.fullbuildcontext(ns_make(ns), (cur,) if cur else ()),
                     self.value_sv("defaultct"))
        cntxt = self.value_sv("defaultct")
        for n in ns:
            self.ck_contradiction(n, cntxt, "assertion")

    def run_snepsul(self, text: str, echo: bool = False) -> Any:
        """Evaluate every SNePSUL form in TEXT; returns the last result."""
        old = self.inunit
        self.inunit = InputStream(text=text, echo=self.outunit if echo else None)
        result: Any = None
        try:
            while True:
                form = self.snepsul_reader().read()
                if form is EOF:
                    break
                result = self.topsneval(form).value
        finally:
            self.inunit = old
        return result

    def sneps_load(self, path: str) -> None:
        """Execute a file of SNePSUL commands silently, batching assertions."""
        self.assert_later += 1
        try:
            with self.let(outunit=NullOutputStream()):
                text = open(self.translate_path(path), encoding="utf-8", errors="replace").read()
                self.run_snepsul(text + "\n")
        finally:
            props = self.new_propositions
            self.new_propositions = []
            self.assert_later -= 1
            self.batch_assert(props)

    def load_python_file(self, path: str) -> None:
        """Run the Python file PATH in the network's Python namespace."""
        path = self.translate_path(path)
        with open(path, encoding="utf-8") as fh:
            source = fh.read()
        exec(compile(source, path, "exec"), self.python.namespace)

    # ------------------------------------------------------------------
    # belief revision hooks
    def is_add_command(self, command: Any) -> bool:
        if not isinstance(command, list) or not command:
            return False
        return _is(command[0], "add") or (len(command) > 1 and isinstance(command[1], list)
                                          and command[1] and _is(command[1][0], "add"))

    def remove_new_hyp(self, command: Any) -> None:
        if _is(command[0], "add"):
            addcommand = ["assert"] + command[1:]
        else:
            addcommand = ["assert"] + command[1][1:]
        newhyp = self.topsneval(addcommand).value
        name = self.crntctname
        self.write(f"Changing the hypothesis set of {name}.\n")
        ct = self.get_context(name)
        self._change_context_name(ns_compl(ct.hyps, _as_ns(newhyp)), name)

    def _request_new_hyp(self) -> Optional[Node]:
        self.write("\n Enter a hypothesis using the SNePSUL command `assert': ")
        while True:
            self.write("\n=><= ")
            ans = self.sneps_read() if self.inunit is not None else EOF
            if ans is EOF:
                return None
            form = (list(ans) if isinstance(ans, list) else [ans]) + [":context", self.crntct]
            ns = self.topsneval(form).value
            if ns:
                return ns[0]
            self.write("\n Oops... something went wrong\n Would you try to enter again?")
            if not self._user_says_yes():
                return None


def _as_ns(x: Any) -> tuple:
    if x is None:
        return ()
    if isinstance(x, tuple):
        return x
    if isinstance(x, list):
        return tuple(x)
    return (x,)


def _default_sneps_directory() -> str:
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(here, "data")


__all__ = ["COMMANDS", "Command", "Result", "SnepsulMixin", "define_command", "environments",
           "sym_name"]
