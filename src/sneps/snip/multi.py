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
"""The MULTI process system (``multi/``, ``snip/fns/sched``).

A SNIP process is a set of named registers.  Running a process calls its
process function with a :class:`Frame` holding a copy of the registers; the
function writes the frame back when it finishes.  Meanwhile :meth:`MultiMixin.regfetch` and
:meth:`MultiMixin.regstore` read and write the stored registers directly,
so -- exactly as in SNePS -- values fetched from a running process are the
ones it started with, and a store into a running process is overwritten
when it finishes (act processes are the exception: they never write back).
"""

from __future__ import annotations

from collections import deque
from typing import Any, Optional

from ..core.network import SNePSError

HIGH = "HIGH"
LOW = "LOW"
INTEND = "INTEND"

REGISTERS = {
    "rule": ("NAME", "TYPE", "NODE", "KNOWN_INSTANCES", "REPORTS", "REQUESTS",
             "INCOMING_CHANNELS", "OUTGOING_CHANNELS", "RULE_USE_CHANNELS",
             "INTRODUCTION_CHANNELS", "PENDING_FORWARD_INFERENCES", "PRIORITY",
             "RULE_HANDLER", "USABILITY_TEST"),
    "num-quant.rule": ("NAME", "TYPE", "NODE", "KNOWN_INSTANCES", "NUM_QUANT_POS_INSTANCES",
                       "NUM_QUANT_NEG_INSTANCES", "REPORTS", "REQUESTS", "INCOMING_CHANNELS",
                       "OUTGOING_CHANNELS", "RULE_USE_CHANNELS", "INTRODUCTION_CHANNELS",
                       "PENDING_FORWARD_INFERENCES", "PRIORITY", "RULE_HANDLER",
                       "USABILITY_TEST"),
    "non-rule": ("NAME", "NODE", "KNOWN_INSTANCES", "REPORTS", "REQUESTS",
                 "INCOMING_CHANNELS", "OUTGOING_CHANNELS", "PENDING_FORWARD_INFERENCES",
                 "PRIORITY"),
    "user": ("NAME", "REPORTS", "CONTEXT_NAME", "DEDUCED_NODES", "TOTAL_DESIRED",
             "POS_DESIRED", "NEG_DESIRED", "POS_FOUND", "NEG_FOUND", "CLIENT", "PRIORITY"),
    "whuser": ("NAME", "VARS", "REPORTS", "CONTEXT_NAME", "DEDUCED_NODES", "TOTAL_DESIRED",
               "POS_DESIRED", "NEG_DESIRED", "POS_FOUND", "NEG_FOUND", "CLIENT", "PRIORITY"),
    "act": ("NAME", "NODE", "CONTEXT_NAME", "REPORTS", "PRECONDITIONS", "EFFECTS", "PLANS",
            "AGENDA", "PRIORITY"),
}
REGISTERS["posuser"] = REGISTERS["neguser"] = REGISTERS["user"]
REGISTERS["notwhuser"] = REGISTERS["whuser"]

_counter = [0]


class Process:
    """A MULTI process: a process function name and its registers."""

    __slots__ = ("slots", "id", "__weakref__")

    def __init__(self, name: str, *values: Any):
        regs = REGISTERS[name]
        if len(values) + 1 != len(regs):
            raise TypeError(f"process {name} needs {len(regs) - 1} register values")
        self.slots = dict(zip(regs, (name,) + values))
        _counter[0] += 1
        self.id = f"p{_counter[0]}"

    @property
    def name(self) -> str:
        return self.slots["NAME"]

    def __repr__(self) -> str:
        return self.id


class Frame:
    """The register bindings of a running process."""

    def __init__(self, slots: dict):
        self.__dict__.update(slots)

    def to_slots(self, regs: tuple) -> dict:
        return {r: self.__dict__[r] for r in regs}


class StopInference(Exception):
    """THROW to Stop-Handled-by-Contradiction-Handler."""


class MultiMixin:
    """Process queues and the MULTI scheduler, mixed into :class:`~sneps.Network`."""

    interrupt_requested = False

    def _init_multi(self) -> None:
        self.act_queue: deque = deque()
        self.high_queue: deque = deque()
        self.low_queue: deque = deque()
        self.use_one_queue_only = False
        self.f: Optional[Frame] = None        # registers of the running process
        self.curnt: Optional[Process] = None  # the running process
        self.trace_initiated: Any = None
        self.trace_events: Any = None

    @staticmethod
    def regfetch(p: Process, reg: str) -> Any:
        return p.slots[reg]

    @staticmethod
    def regstore(p: Process, reg: str, value: Any) -> Any:
        p.slots[reg] = value
        return value

    def write_back(self, frame: Frame) -> None:
        """PROCESS-CHANGE-SLOTS of the running process."""
        p = self.curnt
        if p is not None:
            p.slots = frame.to_slots(REGISTERS[p.slots["NAME"]])

    def clear_all_queues(self) -> None:
        self.high_queue = deque()
        self.low_queue = deque()
        self.act_queue = deque()

    @staticmethod
    def _in_queue(p: Process, q: deque) -> bool:
        return any(x is p for x in q)

    def schedule(self, p: Process, q: deque) -> deque:
        if p.slots.get("PRIORITY") == INTEND:
            q.appendleft(p)
        elif self._in_queue(p, q):
            pass
        elif p.slots["NAME"] == "user":
            q.appendleft(p)
        else:
            q.append(p)
        return q

    def initiate(self, p: Process) -> None:
        pri = p.slots.get("PRIORITY")
        if self.use_one_queue_only:
            q = self.high_queue
        elif pri == HIGH:
            q = self.high_queue
        elif pri == LOW:
            q = self.low_queue
        elif pri == INTEND:
            q = self.act_queue
        else:
            return
        if self.trace_initiated and not self._in_queue(p, q) and (
                self.trace_initiated is True or p.slots["NAME"] in self.trace_initiated):
            self.write(f"\n** Initiate process {p.slots['NAME']} with id: {p.id}\n")
        self.schedule(p, q)

    def multip(self, actq: deque, hpq: deque, lpq: deque) -> None:
        """Run processes until all queues are empty (high, then low, then acts)."""
        saved = (self.act_queue, self.high_queue, self.low_queue, self.curnt, self.f)
        self.act_queue, self.high_queue, self.low_queue = actq, hpq, lpq
        try:
            while True:
                if self.high_queue:
                    q = self.high_queue
                elif self.low_queue:
                    q = self.low_queue
                elif self.act_queue:
                    q = self.act_queue
                else:
                    return
                if self.interrupt_requested:
                    self.interrupt_requested = False
                    raise SNePSError("Interrupted by the user", "multi", "multip")
                p = q.popleft()
                self._run_process(p)
        finally:
            self.act_queue, self.high_queue, self.low_queue, self.curnt, self.f = saved

    def interrupt(self) -> None:
        """Ask a running inference to stop (safe to call from another thread)."""
        self.interrupt_requested = True

    def _run_process(self, p: Process) -> None:
        name = p.slots["NAME"]
        frame = Frame(p.slots)
        old_curnt, old_f = self.curnt, self.f
        self.curnt, self.f = p, frame
        try:
            if self.trace_events and (self.trace_events is True or name in self.trace_events):
                self.write(f"\n>>>>>> Entering process id = {p.id}\n")
            self.PROCESS_FUNCTIONS[name](self, frame)
        finally:
            self.curnt, self.f = old_curnt, old_f

    PROCESS_FUNCTIONS: dict = {}
