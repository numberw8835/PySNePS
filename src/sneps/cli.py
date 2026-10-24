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
"""Command-line entry points: ``sneps`` (SNePSUL) and ``snepslog`` (SNePSLOG).

Both start an interactive read-eval-print loop on a fresh network, after
optionally restoring a saved network, loading files, evaluating commands
given with ``-e`` and running a demo.  ``--batch`` skips the interactive
part, which makes the commands usable in scripts::

    snepslog --batch --demo sneps:demo;snepslog;socrates.snlog
    sneps --batch -e "(define member class)" -e "(assert member Socrates class man)" \\
          --save socrates.json
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Optional, Sequence

from . import __version__
from .io.streams import ConcatenatedInputStream, InputStream


def _parser(prog: str, snepslog: Optional[bool]) -> argparse.ArgumentParser:
    lang = "SNePSLOG" if snepslog else "SNePSUL"
    p = argparse.ArgumentParser(
        prog=prog,
        description=f"PySNePS {__version__}: the SNePS 2.8 knowledge representation and "
                    f"reasoning system. Starts a {lang} read-eval-print loop."
        if snepslog is not None else
        f"PySNePS {__version__}: the SNePS 2.8 knowledge representation and reasoning "
        "system. Starts a SNePSUL (or, with --snepslog, SNePSLOG) read-eval-print loop.")
    if snepslog is None:
        p.add_argument("--snepslog", action="store_true", help="use SNePSLOG instead of SNePSUL")
    p.add_argument("--restore", metavar="FILE",
                   help="start from a saved network (a JSON file written by --save or outnet)")
    p.add_argument("--load", metavar="FILE", action="append", default=[],
                   help="load a file silently before starting: SNePSUL (.sneps), SNePSLOG "
                        "(.snlog) or Python (.py, run with `net` in scope, e.g. to define "
                        "primitive actions); may be repeated")
    p.add_argument("-e", "--eval", metavar="INPUT", action="append", default=[],
                   help="evaluate a command as if typed at the prompt; may be repeated")
    p.add_argument("--demo", metavar="FILE",
                   help="run a demo file (a path, or a logical path like "
                        "sneps:demo;sneps;bidir.sneps)")
    p.add_argument("--pause", action="store_true", help="show the demo pause message")
    p.add_argument("--batch", action="store_true",
                   help="exit after the -e inputs and the demo instead of reading stdin")
    p.add_argument("--fold-case", action="store_true",
                   help="read names in lower case, so that Man and man are the same "
                        "(the default keeps their case)")
    p.add_argument("-q", "--quiet", action="store_true", help="don't print the banner")
    p.add_argument("--save", metavar="FILE",
                   help="save the network on exit (as JSON)")
    p.add_argument("--export", metavar="DIR",
                   help="write a machine-learning dataset of the network on exit "
                        "(see sneps.ml.export_dataset)")
    p.add_argument("--classic", action="store_true",
                   help="use the plain read-eval-print loop instead of the full-screen "
                        "interface (the default in a terminal)")
    p.add_argument("--version", action="version", version=f"PySNePS {__version__}")
    return p


def _use_tui(args: argparse.Namespace, stdin: Any, stdout: Any) -> bool:
    if args.batch or args.classic or stdin is not None or stdout is not None:
        return False
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return False
    from .tui import available
    if not available():
        print("(prompt_toolkit is not installed, so the full-screen interface is not "
              "available; starting the classic loop)", file=sys.stderr)
        return False
    return True


def _quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _load(net, path: str) -> None:
    low = path.lower()
    if low.endswith((".snlog", ".snepslog")):
        net.snepslog_load(path)
    elif low.endswith(".py"):
        net.load_python_file(path)
    else:
        net.sneps_load(path)


def run(argv: Optional[Sequence[str]] = None, snepslog: Optional[bool] = False,
        prog: str = "sneps", stdin=None, stdout=None) -> int:
    """Run the command line ARGV; SNEPSLOG None means "decided by --snepslog"."""
    args = _parser(prog, snepslog).parse_args(argv)
    if snepslog is None:
        snepslog = args.snepslog
    use_tui = _use_tui(args, stdin, stdout)
    from .network import Network
    stdin = stdin if stdin is not None else sys.stdin
    net = Network(output=stdout if stdout is not None else sys.stdout)
    if args.fold_case:
        net.fold_case = "lower"
    if args.restore:
        from .io import load_network
        load_network(net, args.restore)
    for path in args.load:
        _load(net, path)
    lines = list(args.eval)
    if args.demo:
        pause = " av" if args.pause else ""
        lines.append(f"demo {_quote(args.demo)}{pause}" if snepslog
                     else f"(demo {_quote(args.demo)}{pause})")
    if use_tui:
        from .tui import run_tui
        run_tui(net, "snepslog" if snepslog else "sneps", lines, welcome=not args.quiet)
        return _finish(net, args)
    text = "".join(line + "\n" for line in lines)
    inunit: InputStream = InputStream(text=text)
    if not args.batch:
        inunit = ConcatenatedInputStream(inunit, InputStream.from_textio(stdin))
    if snepslog:
        net.snepslog_repl(inunit=inunit, hello=not args.quiet)
    else:
        net.sneps(inunit=inunit, banner=not args.quiet)
    net.outunit.flush()
    return _finish(net, args)


def _finish(net: Any, args: argparse.Namespace) -> int:
    if args.save:
        from .io import save_network
        save_network(net, args.save)
    if args.export:
        net.export_dataset(args.export)
    return 0


def sneps_main(argv: Optional[Sequence[str]] = None) -> int:
    """The ``sneps`` command: a SNePSUL read-eval-print loop."""
    return run(argv, snepslog=False, prog="sneps")


def snepslog_main(argv: Optional[Sequence[str]] = None) -> int:
    """The ``snepslog`` command: a SNePSLOG read-eval-print loop."""
    return run(argv, snepslog=True, prog="snepslog")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """``python -m sneps [--snepslog] ...``"""
    return run(argv, snepslog=None, prog="python -m sneps")


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
