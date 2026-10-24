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
"""The full-screen interface (sneps.tui), driven with keystrokes through a
pipe and checked through its state."""

from __future__ import annotations

import queue
import threading
import time

import pytest

pytest.importorskip("prompt_toolkit")

from prompt_toolkit.data_structures import Size  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from sneps import Network  # noqa: E402
from sneps.tui.app import NO_ANSWER, SnepsTUI  # noqa: E402
from sneps.tui.engine import Bridge  # noqa: E402
from sneps.tui.text import HELP_ALIASES, HELP_TOPICS, help_topic, parse_menu  # noqa: E402

F1, F2, F3, ESC, ENTER = "\x1bOP", "\x1bOQ", "\x1bOR", "\x1b", "\r"
CTRL_L = "\x0c"
LEFT, RIGHT = "\x1b[D", "\x1b[C"
PASTE = "\x1b[200~{}\x1b[201~"          # bracketed paste


class _Screen(DummyOutput):
    def get_size(self) -> Size:
        return Size(rows=40, columns=120)


def wait_until(pred, timeout: float = 15.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def shown(text: str):
    return lambda tui: any(text in line for line in tui.lines)


def idle(kind: str):
    return lambda tui: (not tui.bridge.busy and tui.snap.kind == kind and tui.dialog is None
                        and tui.bridge.events.empty())


def run_session(steps, mode: str = "snepslog") -> SnepsTUI:
    """Run the interface, typing each step's keys and waiting for its condition."""
    errors: list = []
    with create_pipe_input() as inp:
        tui = SnepsTUI(mode=mode, input=inp, output=_Screen(), welcome=False)

        def driver() -> None:
            try:
                if not wait_until(lambda: tui.loop is not None and idle(mode)(tui)):
                    errors.append("the session did not start")
                    return
                for keys, ready in steps:
                    inp.send_text(keys)
                    if not wait_until(lambda: ready(tui)):
                        errors.append(f"timed out after {keys!r}")
                        return
            finally:
                if tui.loop is not None:
                    tui.loop.call_soon_threadsafe(tui.quit)
        thread = threading.Thread(target=driver, daemon=True)
        thread.start()
        tui.run()
        thread.join(5)
    assert not errors, errors
    return tui


def test_tell_ask_and_side_panel():
    tui = run_session([
        ("man(Socrates)." + ENTER, shown("wff1!:  man(Socrates)")),
        ("all(x)(man(x) => mortal(x))." + ENTER, shown("wff2!:")),
        ("mortal(?who)?" + ENTER, shown("wff3!:  mortal(Socrates)")),
        ("mortal(Zeus)?" + ENTER, shown(NO_ANSWER)),
        ("Socrates is a man" + ENTER, shown("statements end with")),
    ])
    beliefs = {b.label: (b.text, b.hypothesis) for b in tui.kb.beliefs}
    assert beliefs["wff1"] == ("man(Socrates)", True)
    assert beliefs["wff3"] == ("mortal(Socrates)", False)      # derived
    assert "Socrates" in tui.kb.terms
    assert any(line.startswith("snepslog❯ mortal(?who)?") for line in tui.lines)


def test_contradictions_are_answered_from_a_menu():
    tui = run_session([
        (PASTE.format("man(Socrates).\nall(x)(man(x) => mortal(x)).\nmortal(Socrates)?") + ENTER,
         shown("wff3!:  mortal(Socrates)")),
        ("~mortal(Socrates)." + ENTER, lambda t: t.dialog is not None),
        ("d", idle("snepslog")),          # discard the new assertion
    ])
    texts = [b.text for b in tui.kb.beliefs]
    assert "mortal(Socrates)" in texts and "~mortal(Socrates)" not in texts
    assert any(line == "answer❯ d" for line in tui.lines)


def test_help_follows_the_mode():
    def page(key):
        return lambda t: getattr(t.dialog, "help", None) is not None and t.dialog.help.key == key
    tui = run_session([
        (F1, page("mode1")),                    # SNePSLOG mode 1: its page
        (RIGHT, page("mode2")),
        ("5", page("snepsul")),
        (LEFT, page("mode3")),
        (ESC, lambda t: t.dialog is None),
        ("help python" + ENTER, page("python")),
        (ESC, lambda t: t.dialog is None),
        ("help nonsense" + ENTER, lambda t: page("mode1")(t) and "no help page" in t.flash),
        (ESC, lambda t: t.dialog is None),
        (F2, lambda t: t.dialog is not None),
        ("s", idle("sneps")),
        (F1, page("snepsul")),                  # SNePSUL: its page
        (F1, lambda t: t.dialog is None),        # F1 again closes it
    ])
    assert "now talking SNePSUL" in "\n".join(tui.lines)


def test_help_pages():
    names = [name for name, _, _ in HELP_TOPICS]
    assert names == ["start", "mode1", "mode2", "mode3", "snepsul", "python", "questions",
                     "keys"]
    for name, label, text in HELP_TOPICS:
        assert text.strip() and label
        assert max(len(line) for line in text.splitlines()) <= 72, name   # fits 80 columns
    assert set(HELP_ALIASES.values()) <= set(names)
    assert help_topic("snepslog", "snepslog", 3) == "mode3"
    assert help_topic("sneps", "sneps", 1) == "snepsul"
    assert help_topic("more", "sneps", 1) == "snepsul"
    assert help_topic("escape", "snepslog", 1) == "python"
    assert help_topic("answer", "snepslog", 2) == "questions"


def test_clearing_the_transcript():
    def empty(t) -> bool:
        return not any(line.strip() for line in t.lines)
    tui = run_session([
        ("man(Socrates)." + ENTER, shown("wff1!:  man(Socrates)")),
        (CTRL_L, empty),
        ("man(Plato)." + ENTER, shown("wff2!:  man(Plato)")),
        ("clear" + ENTER, empty),
    ])
    assert [b.text for b in tui.kb.beliefs] == ["man(Socrates)", "man(Plato)"]
    assert "Transcript cleared" in (tui.flash or "")


def test_switching_languages():
    tui = run_session([
        (F2, lambda t: t.dialog is not None),
        ("s", idle("sneps")),
        ("(define member class)" + ENTER, shown("(member class)")),
        ("(describe (assert member Plato class man))" + ENTER, shown("(M1! (class man)")),
        (F2, lambda t: t.dialog is not None),
        ("p", idle("python")),
        ("len(net.all_nodes())" + ENTER, lambda t: "3" in t.lines and idle("python")(t)),
        (F2, lambda t: t.dialog is not None),
        ("1", idle("snepslog")),
        ("^^" + ENTER, idle("escape")),
        ("6 * 7" + ENTER, lambda t: "42" in t.lines),
        ("def double(x):" + ENTER, idle("pymore")),
        ("    return 2 * x" + ENTER, idle("pymore")),
        (ENTER, idle("escape")),
        ("double(21)" + ENTER, lambda t: t.lines.count("42") == 2),
        ("^^" + ENTER, idle("snepslog")),
        ("^ net.python.namespace['double'](4)" + ENTER, shown("8")),
    ])
    assert any("now talking SNePSUL" in line for line in tui.lines)
    assert any("now talking Python" in line for line in tui.lines)
    assert any("now talking SNePSLOG" in line for line in tui.lines)


def test_help_and_demos():
    tui = run_session([
        (F1, lambda t: getattr(t.dialog, "is_help", False)),
        (ESC, lambda t: t.dialog is None),
        (F3, lambda t: t.dialog is not None),
        (ENTER, lambda t: shown("demonstration.")(t) and idle("snepslog")(t)),
    ])
    assert any("mortal(socrates)" in line for line in tui.lines)


def test_menu_parser():
    contradiction = """ You have the following options:
  1. [a] to attempt to resolve the contradiction automatically
  2. [c] to continue anyway, knowing that a contradiction is derivable;
  3. [r] to revise the inconsistent part of the context manually
  4. [d] to discard this contradictory new assertion from the context
 (please type a, c, r or d)""".splitlines()
    assert [(o.answer, o.label) for o in parse_menu(contradiction)] == [
        ("a", "Attempt to resolve the contradiction automatically"),
        ("c", "Continue anyway, knowing that a contradiction is derivable"),
        ("r", "Revise the inconsistent part of the context manually"),
        ("d", "Discard this contradictory new assertion from the context")]
    culprit = contradiction + ["=><= ", " Please choose from the following hypotheses the one",
                               " that you would least like to keep:", "",
                               " 1 :   wff1!:  man(Socrates)", " (2 supported propositions)",
                               " 2 :   wff2!:  all(x)(man(x) => mortal(x))"]
    assert [o.answer for o in parse_menu(culprit)] == ["1", "2"]
    verbs = [" [d]iscard from the context, [k]eep in the context,",
             " [u]ndecided, [q]uit revising this set, [i]nstructions",
             " (please type d, k, u, q or i)"]
    assert [o.label for o in parse_menu(verbs)][:2] == ["Discard from the context",
                                                         "Keep in the context"]
    assert [o.answer for o in parse_menu([" Enter 'y' or 'n' (if unsure, say 'n')"])] == ["y", "n"]
    assert parse_menu([" Enter a hypothesis using SNePSLOG all on one line."]) == []


def test_bridge_interrupts_a_long_inference():
    net = Network(output=False)
    run = net._run_process

    def slow(p):
        time.sleep(0.02)
        run(p)
    net._run_process = slow
    bridge = Bridge(net, "snepslog")
    bridge.start()
    output: list = []

    def until_waiting():
        while True:
            kind, payload = bridge.events.get(timeout=20)
            if kind == "output":
                output.extend(payload)
            elif kind == "waiting":
                return payload
    until_waiting()
    bridge.send("\n".join(f"all(x)(p{i}(x) => p{i + 1}(x))." for i in range(1, 9))
                + "\np1(a).")
    while bridge.busy or not bridge.events.empty():
        snap = until_waiting()
    bridge.send("p9(a)?")
    time.sleep(0.3)
    bridge.interrupt()
    snap = until_waiting()
    assert snap.kind == "snepslog"
    assert any("Interrupted by the user" in line for line in output)
    bridge.stop()
    try:
        until_waiting()
    except queue.Empty:
        pass
