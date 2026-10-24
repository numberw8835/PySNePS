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
"""Runs a SNePS top level in a background thread for the TUI.

The real read-eval-print loops (SNePSLOG, SNePSUL, the Python escapes,
demos and the belief-revision questions) run unchanged; the bridge gives them an
input stream that waits for the user's next line and an output stream that
forwards complete lines to the interface.  Whenever SNePS waits for input the
bridge reports the prompt it printed and, at a top-level prompt, a snapshot
of the knowledge base, taken while the engine is idle.
"""

from __future__ import annotations

import collections
import io
import queue
import threading
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..core.printing import flat_text
from ..host import CONTINUATION, PROMPT as ESCAPE_PROMPT
from ..io.streams import InputStream, OutputStream

#: Sent by the interface to leave the Python top level (never typed by users).
SWITCH = "\x00switch"
PYTHON_PROMPT = ">>> "
TOP_LEVELS = ("snepslog", "sneps", "python")


@dataclass
class Belief:
    label: str            # wff3 / M3
    text: str             # mortal(Socrates) / (class mortal) (member Socrates)
    hypothesis: bool      # told rather than derived


@dataclass
class Snapshot:
    """What the interface needs to know while SNePS waits for input."""
    kind: str                     # snepslog, sneps, python, escape, pymore, answer or more
    prompt: str
    dialect: str = "snepslog"     # the language of the last SNePS top level
    snepslog_mode: int = 1
    context: str = ""
    inconsistent: bool = False
    trace: bool = False
    beliefs: list = field(default_factory=list)
    contexts: list = field(default_factory=list)   # (name, number of hypotheses, current?)
    terms: list = field(default_factory=list)
    recent: list = field(default_factory=list)     # the lines printed before a question


def kind_of_prompt(prompt: str) -> str:
    if prompt in (": ", "*: "):
        return "snepslog"
    if prompt == "* ":
        return "sneps"
    if prompt == PYTHON_PROMPT:
        return "python"
    if prompt == ESCAPE_PROMPT:
        return "escape"
    if prompt == CONTINUATION:
        return "pymore"
    if prompt == "":
        return "more"
    return "answer"


#: Arcs whose base-node arguments (the numbers of min/max/thresh) are SNePS's own.
_INTERNAL_ARCS = {"min-", "max-", "thresh-", "threshmax-", "emin-", "emax-", "etot-"}


def _internal(n: Any) -> bool:
    ups = [r for r in n.fcableset if r.endswith("-")]
    return bool(ups) and all(r in _INTERNAL_ARCS for r in ups)


class _Sink(OutputStream):
    """The engine's output stream: complete lines go to the interface, the
    unfinished last line (a prompt, when SNePS waits) is held back."""

    def __init__(self, bridge: "Bridge"):
        super().__init__(io.StringIO())
        self.bridge = bridge
        self.lock = threading.Lock()
        self.partial = ""
        self.pending: list[str] = []
        self.recent: collections.deque = collections.deque(maxlen=80)
        self.last_flush = 0.0

    def write(self, s: str) -> None:
        if not s:
            return
        nl = s.rfind("\n")
        self.column = len(s) - nl - 1 if nl >= 0 else self.column + len(s)
        with self.lock:
            lines = (self.partial + s).split("\n")
            self.partial = lines.pop()
            self.pending.extend(lines)
            self.recent.extend(lines)
        if self.pending and time.monotonic() - self.last_flush > 0.05:
            self.flush()

    def flush(self) -> None:
        with self.lock:
            lines, self.pending = self.pending, []
        self.last_flush = time.monotonic()
        if lines:
            self.bridge.emit("output", lines)

    def take_partial(self) -> str:
        with self.lock:
            partial, self.partial = self.partial, ""
        return partial


class Bridge:
    """Connects a :class:`~sneps.Network`'s top levels to an interface."""

    def __init__(self, net: Any, mode: str = "snepslog",
                 notify: Callable[[], None] = lambda: None):
        self.net = net
        self.mode = mode
        self.notify = notify
        self.events: queue.Queue = queue.Queue()
        self._lines: queue.Queue = queue.Queue()
        self.sink = _Sink(self)
        self.stream = InputStream(line_source=self._next_line, interactive=True)
        self.next_mode: Optional[str] = None
        self.dialect = mode
        self.busy = True
        self.finished = False
        self._eof = False
        self.thread = threading.Thread(target=self._main, name="sneps-engine", daemon=True)

    # -- called by the interface ------------------------------------------
    def start(self) -> None:
        self.thread.start()

    def send(self, line: Optional[str]) -> None:
        """Give SNePS the next line of input (None ends the session)."""
        self.busy = line is not None
        self._lines.put(line)

    def interrupt(self) -> None:
        self.net.interrupt()

    def stop(self) -> None:
        self._eof = True
        self.send(None)

    # -- called in the engine thread --------------------------------------
    def emit(self, kind: str, payload: Any = None) -> None:
        self.events.put((kind, payload))
        self.notify()

    def _next_line(self) -> Optional[str]:
        prompt = self.sink.take_partial()
        self.sink.flush()
        self.net.interrupt_requested = False
        kind = kind_of_prompt(prompt)
        if kind in ("snepslog", "sneps"):
            self.dialect = kind
        snap = self.snapshot(kind, prompt)
        self.sink.recent.append(prompt)     # marks where the next question starts
        self.busy = False
        self.emit("waiting", snap)
        if self._eof:
            return None
        line = self._lines.get()
        if line is None:
            self._eof = True
            return None
        return line + "\n"

    def snapshot(self, kind: str, prompt: str = "") -> Snapshot:
        """The state of the session; the knowledge base only at a top level.
        Call it only while the engine is idle."""
        net = self.net
        snap = Snapshot(kind, prompt, self.dialect, getattr(net, "snepslog_mode", 1),
                        trace=bool(net.infertrace))
        snap.recent = list(self.sink.recent)
        if kind not in TOP_LEVELS:
            return snap
        try:
            self._fill_kb(snap)
        except Exception:  # a snapshot must never break the session
            pass
        return snap

    def _fill_kb(self, snap: Snapshot) -> None:
        net = self.net
        name = net.crntct if isinstance(net.crntct, str) else str(net.value_sv("defaultct"))
        ct = net.get_context(net.crntct)
        snap.context = name
        snap.inconsistent = bool(ct is not None and (ct.okinconsistent or ct.kinconsistent))
        hyps = {id(h) for h in ct.hyps} if ct is not None else set()
        logic = snap.dialect == "snepslog"
        from ..snepslog.generator import m_to_wff
        beliefs = []
        for n in sorted((n for n in net.all_nodes() if n.is_mol), key=lambda n: n.order):
            if not net.isassert(n):
                continue
            if logic:
                label, text = m_to_wff(n), net.node_text(n)
            else:
                label = n.name
                text = flat_text(net.des1(n, [()])[1:])[1:-1]
            beliefs.append(Belief(label, text, id(n) in hyps))
            if len(beliefs) >= 1000:
                break
        snap.beliefs = beliefs
        snap.contexts = [(nm, len(c.hyps), nm == name)
                         for c in net.allct() for nm in c.names]
        snap.terms = sorted((n.name for n in net.all_nodes() if n.is_base and not _internal(n)),
                            key=str.lower)[:2000]


    # -- the engine thread ------------------------------------------------
    def _main(self) -> None:
        net = self.net
        net.inunit, net.outunit = self.stream, self.sink
        mode = self.mode
        try:
            while not self._eof:
                if mode == "snepslog":
                    net.snepslog_repl(inunit=self.stream, outunit=self.sink, hello=False)
                elif mode == "sneps":
                    net.sneps(inunit=self.stream, outunit=self.sink, banner=False)
                elif not self._python_toplevel():
                    break
                mode, self.next_mode = (self.next_mode or "python"), None
        except Exception:
            self.sink.write("\nPySNePS internal error:\n" + traceback.format_exc())
        finally:
            self.sink.write("\n")
            self.sink.flush()
            self.finished = True
            self.emit("exit")

    def _python_toplevel(self) -> bool:
        """A Python console with the network's namespace (``net`` is the
        network); False at the end of the input."""
        net = self.net
        host = net.python
        lines: list[str] = []
        while True:
            self.sink.write("\n" + (CONTINUATION if lines else PYTHON_PROMPT))
            line, _missing = self.stream.read_line()
            if line is None:
                return False
            if line == SWITCH:
                return True
            if not lines and not line.strip():
                continue
            lines.append(line)
            source = "\n".join(lines)
            try:
                if host.compiler(source, "<sneps>", "single") is None:
                    continue
            except (SyntaxError, OverflowError, ValueError):
                pass
            lines = []
            host.run(source)
            if self.next_mode:
                return True
