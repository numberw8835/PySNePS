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
"""Python as SNePS's host language.

SNePSUL and SNePSLOG escape to the language SNePS runs in: ``^ expr``
evaluates one Python expression (or statement) and ``^^`` starts reading
Python until a line ``^^``.  The code runs in a namespace that belongs to
the network and holds:

``net``
    the :class:`~sneps.Network`;
``print``, ``fresh_line``, ``help``
    printing (and Python's help) to SNePS's output;
``node(name)``
    the node called NAME (or None);
``snepsul(text, *args)``, ``tell(text, *args)``
    running SNePSUL or SNePSLOG input (``{}`` in TEXT is replaced by the
    arguments written as SNePSUL names);
``@primaction``, ``attach_primaction(action, function)``
    defining primitive actions and attaching them to action nodes;
``@attached_function``, ``attach_function(predicate, function)``
    procedural attachment;
``@command``, ``undefine_commands(*names)``
    defining SNePSUL commands.
"""

from __future__ import annotations

import ast
import builtins
import codeop
import inspect
import traceback
from typing import Any, Callable, Iterable, Optional

from .core.network import SNePSError
from .core.node import Node
from .core.printing import Text, escape_name, number_text

PROMPT = "^^> "
CONTINUATION = "... "


def snepsul_text(x: Any) -> str:
    """X written as SNePSUL: nodes and names as (escaped) names, sequences
    in parentheses, strings in double quotes."""
    if isinstance(x, Node):
        return escape_name(x.name)
    if isinstance(x, Text):
        return '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(x, str):
        return escape_name(x)
    if x is None:
        return "nil"
    if x is True:
        return "t"
    if isinstance(x, (list, tuple, set, frozenset)):
        return "(" + " ".join(snepsul_text(e) for e in x) + ")"
    if isinstance(x, (int, float)):
        return number_text(x)
    return escape_name(str(x))


class PythonHost:
    """The Python namespace of one network and the ``^``/``^^`` escapes."""

    def __init__(self, net: Any):
        self.net = net
        self.compiler = codeop.CommandCompiler()
        self.namespace: dict = {
            "__name__": "__sneps__",
            "__builtins__": builtins,
            "net": net,
            "Node": Node,
            "SNePSError": SNePSError,
            "print": self.print,
            "help": self.help,
            "fresh_line": lambda: net.fresh_line(),
            "node": lambda name: net.node(net.fold_name(str(name))),
            "snepsul": self.snepsul,
            "tell": self.tell,
            "primaction": self.primaction,
            "attach_primaction": self.attach_primaction,
            "attached_function": self.attached_function,
            "attach_function": self.attach_function,
            "command": self.command,
            "undefine_commands": self.undefine_commands,
        }

    # ------------------------------------------------------------------
    # evaluation
    def evaluate(self, source: str) -> Any:
        """The value of the Python expression SOURCE, or None after running
        SOURCE as statements."""
        source = source.strip()
        if not source:
            return None
        try:
            code = compile(source, "<sneps>", "eval")
        except SyntaxError:
            exec(compile(source, "<sneps>", "exec"), self.namespace)
            return None
        return eval(code, self.namespace)

    def run(self, source: str, show: bool = True) -> None:
        """Run SOURCE as the console does: the value of a final expression
        statement is printed.  Errors are reported, not raised."""
        net = self.net
        try:
            tree = ast.parse(source, "<sneps>", "exec")
            last = tree.body[-1] if tree.body else None
            if show and isinstance(last, ast.Expr):
                exec(compile(ast.Module(tree.body[:-1], type_ignores=[]), "<sneps>", "exec"),
                     self.namespace)
                value = eval(compile(ast.Expression(last.value), "<sneps>", "eval"),
                             self.namespace)
                if value is not None:
                    net.fresh_line()
                    net.write(repr(value) + "\n")
                    self.namespace["_"] = value
            else:
                exec(compile(tree, "<sneps>", "exec"), self.namespace)
        except SyntaxError as e:
            net.fresh_line()
            net.write("".join(traceback.format_exception_only(type(e), e)))
        except SNePSError as e:
            net._report_sneps_error(e)
        except SystemExit:
            net.fresh_line()
            net.write("exit() does not leave SNePS here: type ^^ to return from Python, "
                      "and exit at a SNePS prompt\n")
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.report(e)

    def report(self, e: BaseException) -> None:
        """Print the traceback of E without the frames of this module."""
        tb = e.__traceback__
        while tb is not None and tb.tb_frame.f_code.co_filename == __file__:
            tb = tb.tb_next
        self.net.fresh_line()
        self.net.write("".join(traceback.format_exception(type(e), e, tb)))

    def loop(self, stream: Any = None, prompt: str = PROMPT,
             exit_words: Iterable[str] = ("^^",)) -> None:
        """Read and run Python from STREAM (SNePS's input) until a line
        holding one of EXIT_WORDS, or the end of the input."""
        net = self.net
        stream = stream if stream is not None else net.inunit
        exit_words = tuple(exit_words)
        lines: list[str] = []
        while True:
            net.fresh_line()
            net.write(CONTINUATION if lines else prompt)
            line, _missing = stream.read_line() if stream is not None else (None, True)
            if line is None:
                return
            if not lines and line.strip() in exit_words:
                return
            if not lines and not line.strip():
                continue
            lines.append(line)
            source = "\n".join(lines)
            try:
                complete = self.compiler(source, "<sneps>", "single")
            except (SyntaxError, OverflowError, ValueError):
                complete = True     # run() reports the error
            if complete is None:
                continue
            lines = []
            self.run(source)

    # ------------------------------------------------------------------
    # the namespace's functions
    def print(self, *args: Any, sep: str = " ", end: str = "\n", file: Any = None,
              flush: bool = False) -> None:
        if file is not None:
            builtins.print(*args, sep=sep, end=end, file=file, flush=flush)
            return
        self.net.write(sep.join(str(a) for a in args) + end)

    def help(self, obj: Any = None) -> None:
        """Python's help(OBJ), written to SNePS's output."""
        import pydoc
        if obj is None:
            self.net.write("help(object) shows the documentation of object, for example "
                           "help(net.ask).\n")
            return
        self.net.write(pydoc.render_doc(obj, renderer=pydoc.plaintext))

    def snepsul(self, text: str, *args: Any) -> Any:
        """Evaluate the SNePSUL forms in TEXT; returns the value of the last.
        A form whose head is a command runs that command, whatever the
        environments it is allowed in (so ``build`` works too), and SNePS
        errors are raised as :class:`~sneps.SNePSError`."""
        from .snepsul.reader import read_all
        if args:
            text = text.format(*[snepsul_text(a) for a in args])
        net = self.net
        result: Any = None
        for form in read_all(text, net.fold_case, macros=True):
            if isinstance(form, list) and form and net.is_com(form[0]):
                result = net.call_command(form).value
            else:
                result = net.topsneval(form).value
        return result

    def tell(self, text: str, *args: Any) -> Any:
        """Give TEXT to SNePSLOG, printing the results."""
        if args:
            text = text.format(*[snepsul_text(a) for a in args])
        return self.net.tell(text, quiet=False)

    def primaction(self, fn: Optional[Callable] = None, *, name: Optional[str] = None) -> Any:
        """Decorator: define a primitive action.  Each parameter of the
        function names an arc of the act and receives the tuple of nodes at
        that arc; a parameter called ``act`` receives the act node itself."""
        def define(f: Callable) -> Callable:
            self.net.define_primaction(name or f.__name__, _act_caller(f))
            f.primaction_name = name or f.__name__
            return f
        return define(fn) if fn is not None else define

    def attach_primaction(self, action: Any, function: Any = None) -> None:
        """Attach a primitive action to the action node ACTION (a node or a
        name).  FUNCTION is a function made with ``@primaction``, the name of
        one (such as the built-in ``believe`` or ``snsequence``), or omitted
        for the action of the same name."""
        net = self.net
        if function is None:
            function = action.name if isinstance(action, Node) else str(action)
        if callable(function):
            fname = getattr(function, "primaction_name", None)
            if fname is None:
                fname = function.__name__
                net.define_primaction(fname, _act_caller(function))
            function = fname
        if not isinstance(action, Node):
            action = net.fold_name(str(action))
        net.attach_primaction(action, net.fold_name(function)
                              if function not in net.primaction_functions else function)

    def attached_function(self, fn: Optional[Callable] = None, *,
                          name: Optional[str] = None) -> Any:
        """Decorator: define a function for procedural attachment.  Each
        parameter names an arc of the predicate node and receives the values
        at that arc (numbers, names, or variable nodes).  The function returns
        a list of ``(sign, {variable: value})`` pairs, the sign being ``"POS"``
        or ``"NEG"``."""
        def define(f: Callable) -> Callable:
            params = list(inspect.signature(f).parameters)

            def attached(net: Any, fnode: Node) -> list:
                args = [tuple(net.ns_to_attachment_arg(fnode.nodeset(p))) for p in params]
                out = []
                for sign, sub in f(*args) or ():
                    pairs = sub.items() if isinstance(sub, dict) else sub
                    out.append((str(sign).upper(), tuple(pairs)))
                return out
            f.attached_function = attached
            return f
        return define(fn) if fn is not None else define

    def attach_function(self, predicate: Any, function: Callable) -> None:
        """Attach FUNCTION (made with ``@attached_function``) to the
        predicate node PREDICATE (a node or a name)."""
        net = self.net
        fn = getattr(function, "attached_function", None)
        if fn is None:
            raise SNePSError(f"{function!r} was not defined with @attached_function")
        node = predicate if isinstance(predicate, Node) \
            else net.value_to_node(net.fold_name(str(predicate)))
        net.attach_function(node, fn)

    def command(self, fn: Optional[Callable] = None, *, name: Optional[str] = None,
                envs: Any = ("top",)) -> Any:
        """Decorator: define a SNePSUL command.  The function receives the
        command's arguments as SNePSUL data (names, numbers, lists); what it
        returns is the command's value."""
        from .snepsul.evaluator import Command, Result, environments

        def define(f: Callable) -> Callable:
            cname = (name or f.__name__).lower()

            def run(net: Any, args: list) -> Result:
                value = f(*args)
                return value if isinstance(value, Result) else \
                    Result(value, net.value_sv("defaultct"))
            self.net.commands[cname] = Command(cname, run, environments(envs, self.net.commands),
                                               doc=f.__doc__)
            return f
        return define(fn) if fn is not None else define

    def undefine_commands(self, *names: str) -> None:
        for n in names:
            self.net.commands.pop(str(n).lower(), None)


def _act_caller(f: Callable) -> Callable[[Any, Node], Any]:
    """F as a primitive action function (called with the network and the act)."""
    params = list(inspect.signature(f).parameters)

    def action(net: Any, act: Node) -> Any:
        return f(*[act if p == "act" else act.nodeset(p) for p in params])
    action.__name__ = f.__name__
    return action
