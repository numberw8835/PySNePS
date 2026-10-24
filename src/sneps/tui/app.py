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
"""The full-screen terminal interface (built with prompt_toolkit).

:class:`SnepsTUI` keeps the session state and talks to the engine through a
:class:`~sneps.tui.engine.Bridge`; the prompt_toolkit layout only displays
that state and turns keys into calls of its methods, so the state can be
tested without a terminal.
"""

from __future__ import annotations

import asyncio
import collections
import os
import re
from typing import Any, Callable, Iterable, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition, has_focus
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import (ConditionalContainer, Float, FloatContainer, HSplit, Layout,
                                   VSplit, Window)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.menus import CompletionsMenu
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from .engine import PYTHON_PROMPT, SWITCH, TOP_LEVELS, Bridge, Snapshot
from .text import (HELP_ALIASES, HELP_TOPICS, HINTS, PROMPTS, SNEPSLOG_COMMANDS, WELCOME,
                   WELCOME_SNEPSUL, Option, fit_text, help_topic, parse_menu)

MODE_NAMES = {"snepslog": "SNePSLOG", "sneps": "SNePSUL", "python": "Python"}
NO_ANSWER = "  ↳ no answer: SNePS can't derive that from what it believes"
PARSE_HINT = "  ↳ statements end with '.', questions with '?', e.g. man(Socrates).  F1: help"
_CPU = re.compile(r"^\s*CPU time : ([0-9.]+)\s*$")
_ECHO = re.compile(r"^(snepslog|sneps|python|python \^\^|answer|…)❯ ")

STYLE = Style.from_dict({
    "header": "bg:#1f3a5f #e8eef7",
    "header.title": "bg:#2f6fb2 #ffffff bold",
    "header.dim": "bg:#1f3a5f #9fb3cc",
    "header.busy": "bg:#1f3a5f #ffd75f bold",
    "header.ready": "bg:#1f3a5f #87d787 bold",
    "header.ask": "bg:#1f3a5f #ffd75f bold",
    "header.warn": "bg:#1f3a5f #ff8787 bold",
    "footer": "bg:#262626 #bcbcbc",
    "footer.key": "bg:#444444 #ffffff bold",
    "hint": "#8a8a8a italic",
    "flash": "#ffd75f bold",
    "sep": "#444444",
    "prompt": "#5fafff bold",
    "prompt.answer": "#ffd75f bold",
    "echo.prompt": "#5fafff",
    "echo.text": "bold",
    "banner": "#87afd7",
    "wff.label": "#808080",
    "wff.asserted": "#87d787",
    "trace": "#af87d7 italic",
    "error": "#ff5f5f bold",
    "warning": "#ffaf5f",
    "note": "#8a8a8a italic",
    "panel.title": "#5fafff bold",
    "panel.hyp": "#87d787",
    "panel.der": "#d7d787",
    "panel.dim": "#6c6c6c",
    "panel.current": "#ffffff bold",
    "dialog": "bg:#1c1c1c #d0d0d0",
    "dialog frame.label": "#ffd75f bold",
    "dialog.text": "#d0d0d0",
    "dialog.dim": "#808080 italic",
    "menu": "#d0d0d0",
    "menu.key": "#ffd75f",
    "menu.selected": "bg:#2f6fb2 #ffffff bold",
    "completion-menu.completion": "bg:#303030 #d0d0d0",
    "completion-menu.completion.current": "bg:#2f6fb2 #ffffff",
    "completion-menu.meta.completion": "bg:#262626 #8a8a8a",
    "completion-menu.meta.completion.current": "bg:#2f6fb2 #d0d0d0",
    "scrollbar.background": "bg:#303030",
    "scrollbar.button": "bg:#6c6c6c",
    "auto-suggestion": "#5f5f5f",
})


# ----------------------------------------------------------------------
# styling of the transcript and the side panel

def _style_transcript_line(line: str) -> list:
    m = _ECHO.match(line)
    if m:
        return [("class:echo.prompt", m.group(0)), ("class:echo.text", line[m.end():])]
    if line.startswith("│"):
        return [("class:banner", line)]
    m = re.match(r"^(\*?: |\* |\^\^> |\.\.\. )(?=\S)", line)     # input echoed by a demo
    if m:
        return [("class:echo.prompt", m.group(0)), ("class:echo.text", line[m.end():])]
    m = re.match(r"^(\s*)(wff\d+)(!?)(:)(.*)$", line)
    if m:
        body = "class:wff.asserted" if m.group(3) else ""
        return [("", m.group(1)), ("class:wff.label", m.group(2) + m.group(3) + m.group(4)),
                (body, m.group(5))]
    if re.match(r"^\s*\(?M\d+!", line):
        return [("class:wff.asserted", line)]
    if re.match(r"^\s*(I wonder if|I know|Since|I infer|holds within|and$|and it is not|"
                r"it is not the case|I wonder about|Because|About to do|Now doing|Intending to|"
                r"Chose to do|The act|has a plan|has no plan|has a precondition|has no precondition|"
                r"has any preconditions|It is satisfied|Believe |Disbelieve )", line):
        return [("class:trace", line)]
    if re.match(r"^\s*(SNePS ERROR|Error|\*\*\*|PySNePS internal error|Traceback)", line):
        return [("class:error", line)]
    if line.startswith("Warning"):
        return [("class:warning", line)]
    if line.startswith(("  ↳", "  (Occurred", "──")):
        return [("class:note", line)]
    return [("", line)]


class _TranscriptLexer(Lexer):
    def lex_document(self, document: Document) -> Callable[[int], list]:
        lines = document.lines
        return lambda i: _style_transcript_line(lines[i]) if i < len(lines) else []


def _style_panel_line(line: str) -> list:
    if line.isupper() or line.startswith(("BELIEFS", "CONTEXTS", "TERMS")):
        return [("class:panel.title", line)]
    if line.startswith(" ●"):
        return [("class:panel.hyp", line[:3]), ("", line[3:])]
    if line.startswith(" ○"):
        return [("class:panel.der", line[:3]), ("", line[3:])]
    if line.startswith(" ▸"):
        return [("class:panel.current", line)]
    if line.startswith(" ("):
        return [("class:panel.dim", line)]
    return [("", line)]


class _PanelLexer(Lexer):
    def lex_document(self, document: Document) -> Callable[[int], list]:
        lines = document.lines
        return lambda i: _style_panel_line(lines[i]) if i < len(lines) else []


def panel_text(snap: Snapshot) -> str:
    """The side panel: beliefs, contexts and terms of the last snapshot."""
    out = [f"BELIEFS · {snap.context or 'default-defaultct'}"]
    if snap.beliefs:
        for b in snap.beliefs:
            out.append(f" {'●' if b.hypothesis else '○'} {b.label}  {b.text}")
        out.append(" (● told  ○ derived)")
    else:
        out.append(" (nothing yet)")
    out += ["", "CONTEXTS"]
    for name, n, current in snap.contexts or [("default-defaultct", 0, True)]:
        out.append(f" {'▸' if current else ' '} {name}  ({n} hypothes{'is' if n == 1 else 'es'})")
    out += ["", "TERMS"]
    if snap.terms:
        line = " "
        for t in snap.terms:
            if len(line) + len(t) > 40 and line.strip():
                out.append(line.rstrip())
                line = " "
            line += t + "  "
        out.append(line.rstrip())
    else:
        out.append(" (none)")
    return "\n".join(out)


# ----------------------------------------------------------------------
# completion

class _Completer(Completer):
    def __init__(self, tui: "SnepsTUI"):
        self.tui = tui

    def get_completions(self, document: Document, event: Any) -> Iterable[Completion]:
        before = document.text_before_cursor
        m = re.search(r"[A-Za-z_][\w\-]*$", before)
        if not m:
            return
        word = m.group(0)
        lead = before[:m.start()]
        kind = self.tui.snap.kind
        low = word.lower()
        if kind == "snepslog" and not lead.strip():
            for cmd, desc in SNEPSLOG_COMMANDS.items():
                if cmd.startswith(low) and cmd != low:
                    yield Completion(cmd, -len(word), display_meta=desc)
        if kind == "sneps" and lead.rstrip().endswith("("):
            for name, cmd in sorted(self.tui.net.commands.items()):
                if name.startswith(low) and name != low:
                    doc = (getattr(cmd, "doc", None) or "").strip().splitlines()
                    yield Completion(name, -len(word), display_meta=doc[0][:50] if doc else "")
        if len(word) >= 2 or lead.strip():
            seen = set()
            for term in self.tui.kb.terms:
                if term.lower().startswith(low) and term != word and term not in seen:
                    seen.add(term)
                    yield Completion(term, -len(word), display_meta="term")


# ----------------------------------------------------------------------
# a keyboard- and mouse-driven list of choices

class ChoiceList:
    def __init__(self, options: list[Option], on_choose: Callable[[Option], None],
                 on_cancel: Callable[[], None], current: int = 0):
        self.options = options
        self.index = max(0, min(current, len(options) - 1))
        self.on_choose = on_choose
        kb = KeyBindings()

        @kb.add("up")
        @kb.add("s-tab")
        def _up(event: Any) -> None:
            self.index = (self.index - 1) % len(self.options)

        @kb.add("down")
        @kb.add("tab")
        def _down(event: Any) -> None:
            self.index = (self.index + 1) % len(self.options)

        @kb.add("enter")
        def _enter(event: Any) -> None:
            self.on_choose(self.options[self.index])

        @kb.add("escape")
        def _esc(event: Any) -> None:
            on_cancel()

        for k, opt in enumerate(options):
            if opt.key and len(opt.key) == 1:
                kb.add(opt.key)(lambda event, opt=opt: self.on_choose(opt))
        self.control = FormattedTextControl(self._fragments, key_bindings=kb, focusable=True,
                                            show_cursor=False)
        self.window = Window(self.control, wrap_lines=True,
                             height=Dimension(min=len(options), max=min(len(options), 16) + 2))

    def _fragments(self) -> list:
        out: list = []
        for k, opt in enumerate(self.options):
            selected = k == self.index

            def click(event: Any, k: int = k) -> None:
                if event.event_type == MouseEventType.MOUSE_UP:
                    self.index = k
                    self.on_choose(self.options[k])
            style = "class:menu.selected" if selected else "class:menu"
            out.append((style, " ❯ " if selected else "   ", click))
            if opt.key:
                out.append((style if selected else "class:menu.key", f"[{opt.key}] ", click))
            out.append((style, opt.label + " ", click))
            out.append(("", "\n"))
        return out


HELP_WIDTH = 86


class HelpPages:
    """The help window: a page for each mode, with tabs to change the page."""

    def __init__(self, tui: "SnepsTUI", key: str):
        self.tui = tui
        self.index = self.index_of(key)
        self.view = TextArea(self._page_text(), read_only=True, scrollbar=True,
                             wrap_lines=True)
        kb = KeyBindings()

        @kb.add("escape")
        @kb.add("q")
        def _close(event: Any) -> None:
            tui.close_dialog()

        @kb.add("right")
        @kb.add("tab")
        def _next(event: Any) -> None:
            self.show((self.index + 1) % len(HELP_TOPICS))

        @kb.add("left")
        @kb.add("s-tab")
        def _previous(event: Any) -> None:
            self.show((self.index - 1) % len(HELP_TOPICS))

        for k in range(len(HELP_TOPICS)):
            kb.add(str(k + 1))(lambda event, k=k: self.show(k))
        self.view.control.key_bindings = kb
        tabs = Window(FormattedTextControl(self._tabs), height=Dimension(min=1, max=2))
        self.body = HSplit([tabs, Window(height=1, char="─", style="class:sep"), self.view])

    @staticmethod
    def index_of(key: str) -> int:
        return next((k for k, (name, _, _) in enumerate(HELP_TOPICS) if name == key), 0)

    @property
    def key(self) -> str:
        return HELP_TOPICS[self.index][0]

    def title(self) -> str:
        return f"Help · {HELP_TOPICS[self.index][1]}   (←/→ other pages · Esc closes)"

    def _width(self) -> int:
        """The width inside the window's frame."""
        return min(HELP_WIDTH, self.tui._columns() - 4) - 2

    def _page_text(self) -> str:
        return fit_text(HELP_TOPICS[self.index][2], self._width() - 1)   # 1: the scrollbar

    def show(self, index: int) -> None:
        self.index = index
        self.view.buffer.set_document(Document(self._page_text(), 0), bypass_readonly=True)
        self.tui.app.invalidate()

    def _tabs(self) -> list:
        """The page tabs, wrapped between tabs if the window is narrow."""
        width = self._width()
        out: list = []
        column = 0
        for k, (_, label, _) in enumerate(HELP_TOPICS):
            def click(event: Any, k: int = k) -> None:
                if event.event_type == MouseEventType.MOUSE_UP:
                    self.show(k)
            text = f" {k + 1} {label} "
            if column and column + len(text) > width:
                out.append(("", "\n"))
                column = 0
            style = "class:menu.selected" if k == self.index else "class:menu"
            out.append((style, text, click))
            column += len(text)
        return out


# ----------------------------------------------------------------------
# the interface

class SnepsTUI:
    """A full-screen terminal interface to one :class:`~sneps.Network`."""

    def __init__(self, net: Any = None, mode: str = "snepslog", commands: Iterable[str] = (),
                 welcome: bool = True, input: Any = None, output: Any = None):
        if net is None:
            from ..network import Network
            net = Network(output=False)
        self.net = net
        self.bridge = Bridge(net, mode, notify=self._wake)
        self.snap = Snapshot("busy", "", mode)
        self.kb = Snapshot("snepslog", ": ", mode)
        self.lines: list[str] = []
        self.pending: collections.deque = collections.deque((c, None) for c in commands)
        self.question = False
        self.saw_output = False
        self.parse_warning = False
        self.suppress = False
        self.follow = True
        self.cpu: Optional[str] = None
        self.flash: Optional[str] = None
        self.show_panel = True
        self.dialog: Optional[Float] = None
        self.last_file = "knowledge.net"
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.exited = False
        if welcome:
            text = WELCOME if mode == "snepslog" else WELCOME_SNEPSUL
            self.lines += ["│ " + line if line else "│" for line in text.rstrip().split("\n")] + [""]
        self._build(input, output)

    # -- layout -------------------------------------------------------------
    def _build(self, input: Any, output: Any) -> None:
        self.transcript = TextArea(text="\n".join(self.lines), read_only=True, scrollbar=True,
                                   wrap_lines=True, lexer=_TranscriptLexer(), focus_on_click=True)
        self.panel = TextArea(read_only=True, scrollbar=True, wrap_lines=True,
                              lexer=_PanelLexer(), width=Dimension.exact(42),
                              focus_on_click=True)
        self.input = TextArea(height=Dimension(min=1, max=6), multiline=True, wrap_lines=True,
                              completer=_Completer(self), complete_while_typing=True,
                              history=InMemoryHistory(), auto_suggest=AutoSuggestFromHistory(),
                              focus_on_click=True)
        self._refresh_panel()
        wide = Condition(lambda: self.show_panel and self._columns() >= 90)
        body = VSplit([self.transcript,
                       ConditionalContainer(VSplit([Window(width=1, char="│", style="class:sep"),
                                                    self.panel]), filter=wide)])
        root = HSplit([
            Window(FormattedTextControl(self._header), height=1, style="class:header"),
            body,
            Window(FormattedTextControl(self._hint), height=1),
            Window(height=1, char="─", style="class:sep"),
            VSplit([Window(FormattedTextControl(self._prompt), dont_extend_width=True),
                    self.input]),
            Window(FormattedTextControl(self._footer), height=1, style="class:footer"),
        ])
        self.floats = FloatContainer(content=root, floats=[
            Float(xcursor=True, ycursor=True, content=CompletionsMenu(max_height=10,
                                                                      scroll_offset=1))])
        self.app = Application(layout=Layout(self.floats, focused_element=self.input),
                               key_bindings=self._keys(), style=STYLE, full_screen=True,
                               mouse_support=True, input=input, output=output,
                               before_render=lambda app: self._drain())

    def _columns(self) -> int:
        try:
            return get_app().output.get_size().columns
        except Exception:
            return 100

    def _header(self) -> list:
        kind = self.snap.kind
        dialect = self.kb.dialect
        if kind == "snepslog" or (kind in ("answer", "more", "busy") and dialect == "snepslog"):
            mode = f"SNePSLOG · mode {self.kb.snepslog_mode}"
        elif kind == "sneps" or kind in ("answer", "more", "busy"):
            mode = "SNePSUL"
        else:
            mode = {"python": "Python", "escape": "Python (^^)", "pymore": "Python"}.get(kind, kind)
        if self.bridge.finished:
            status = ("class:header.warn", " session ended ")
        elif self.bridge.busy:
            status = ("class:header.busy", " working… ")
        elif kind == "answer":
            status = ("class:header.ask", " SNePS is asking you ")
        else:
            status = ("class:header.ready", " ready ")
        # (priority, fragments): the lowest priorities go first when space is short
        parts = [(0, [("class:header.title", " PySNePS "), ("class:header", f" {mode} ")]),
                 (2, [("class:header.dim", "│ context "), ("class:header", f"{self.kb.context} ")]),
                 (3, [("class:header.dim", "│ trace "),
                      ("class:header", "on " if self.kb.trace else "off ")])]
        if self.kb.inconsistent:
            parts.append((1, [("class:header.warn", "│ contradiction ")]))
        if self.cpu:
            parts.append((4, [("class:header.dim", f"│ last {self.cpu}s ")]))
        columns = self._columns()

        def width(ps: list) -> int:
            return sum(len(t) for _, frags in ps for _, t in frags) + len(status[1])
        while width(parts) > columns - 1 and len(parts) > 1:
            parts.remove(max(parts[1:], key=lambda p: p[0]))
        left = [f for _, frags in parts for f in frags]
        return left + [("class:header", " " * max(1, columns - width(parts))), status]

    def _hint(self) -> list:
        if self.flash:
            return [("class:flash", " " + self.flash)]
        if self.bridge.finished:
            return [("class:hint", " " + HINTS["exit"])]
        key = "busy" if self.bridge.busy else self.snap.kind
        return [("class:hint", " " + HINTS.get(key, ""))]

    def _prompt(self) -> list:
        kind = "busy" if self.bridge.busy else self.snap.kind
        label = PROMPTS.get(kind, "…")
        style = "class:prompt.answer" if kind == "answer" else "class:prompt"
        return [(style, f" {label}❯ ")]

    def _footer(self) -> list:
        # (key, label, priority): the highest numbers are dropped first when narrow
        keys = [("F1", "Help", 0), ("F2", "Mode", 1), ("F3", "Demos", 2), ("F4", "Trace", 4),
                ("F5", "Panel", 9), ("^S", "Save", 3), ("^O", "Open", 6), ("^N", "New", 7),
                ("^L", "Clear", 5), ("^C", "Stop", 8), ("^Q", "Quit", 0)]
        columns = self._columns()
        while sum(len(k) + len(label) + 5 for k, label, _ in keys) > columns and len(keys) > 2:
            keys.remove(max(keys, key=lambda k: k[2]))
        out: list = []
        for k, label, _ in keys:
            out += [("class:footer.key", f" {k} "), ("class:footer", f" {label}  ")]
        return out

    # -- keys -----------------------------------------------------------------
    def _keys(self) -> KeyBindings:
        kb = KeyBindings()
        no_dialog = Condition(lambda: self.dialog is None)
        in_input = has_focus(self.input) & no_dialog

        @kb.add("enter", filter=in_input)
        def _submit(event: Any) -> None:
            self.submit()

        @kb.add("escape", "enter", filter=in_input)
        def _newline(event: Any) -> None:
            self.input.buffer.insert_text("\n")

        @kb.add("up", filter=in_input)
        def _up(event: Any) -> None:
            buf = self.input.buffer
            if buf.complete_state:
                buf.complete_previous()
            else:
                buf.auto_up()

        @kb.add("down", filter=in_input)
        def _down(event: Any) -> None:
            buf = self.input.buffer
            if buf.complete_state:
                buf.complete_next()
            else:
                buf.auto_down()

        @kb.add("f1")
        def _help(event: Any) -> None:
            self.toggle_help()

        @kb.add("f2", filter=no_dialog)
        def _mode(event: Any) -> None:
            self.mode_menu()

        @kb.add("f3", filter=no_dialog)
        def _demos(event: Any) -> None:
            self.demo_menu()

        @kb.add("f4", filter=no_dialog)
        def _trace(event: Any) -> None:
            self.toggle_trace()

        @kb.add("f5")
        def _panel(event: Any) -> None:
            self.show_panel = not self.show_panel

        @kb.add("c-s", filter=no_dialog)
        def _save(event: Any) -> None:
            self.save_dialog()

        @kb.add("c-o", filter=no_dialog)
        def _open(event: Any) -> None:
            self.open_dialog()

        @kb.add("c-n", filter=no_dialog)
        def _new(event: Any) -> None:
            self.new_dialog()

        @kb.add("c-l")
        def _clear(event: Any) -> None:
            self.clear_transcript()

        @kb.add("c-c")
        def _interrupt(event: Any) -> None:
            if self.bridge.busy:
                self.bridge.interrupt()
                self.say("Interrupting…")
            elif self.dialog is None:
                self.input.buffer.reset()

        @kb.add("c-q")
        def _quit(event: Any) -> None:
            if self.dialog is not None and getattr(self.dialog, "is_quit", False):
                self.quit()             # Ctrl+Q twice quits without asking
            else:
                self.quit_dialog()

        @kb.add("c-d", filter=in_input & Condition(lambda: not self.input.text))
        def _eof(event: Any) -> None:
            self.quit_dialog()

        @kb.add("pageup", filter=no_dialog)
        def _pgup(event: Any) -> None:
            self.scroll(-1)

        @kb.add("pagedown", filter=no_dialog)
        def _pgdn(event: Any) -> None:
            self.scroll(1)

        @kb.add("c-end", filter=no_dialog)
        def _bottom(event: Any) -> None:
            self.follow = True
            self._refresh_transcript()
            self.app.layout.focus(self.input)

        return kb

    # -- running ---------------------------------------------------------------
    def run(self) -> None:
        self.bridge.start()

        def pre_run() -> None:
            self.loop = asyncio.get_running_loop()
            self._drain()
        try:
            self.app.run(pre_run=pre_run)
        finally:
            self.exited = True
            if not self.bridge.finished:
                self.bridge.stop()

    def _wake(self) -> None:
        loop = self.loop
        if loop is None or self.exited:
            return
        try:
            loop.call_soon_threadsafe(self._invalidate)
        except RuntimeError:
            pass

    def _invalidate(self) -> None:
        self.app.invalidate()

    def _drain(self) -> None:
        """Process what the engine reported (runs in the interface thread)."""
        changed = False
        while True:
            try:
                kind, payload = self.bridge.events.get_nowait()
            except Exception:
                break
            changed = True
            if kind == "output":
                self._on_output(payload)
            elif kind == "waiting":
                self._on_waiting(payload)
            elif kind == "exit":
                self._on_output([""])
        if changed:
            self._refresh_transcript()

    def _on_output(self, lines: list[str]) -> None:
        if self.suppress:
            return
        for raw in lines:
            line = raw.replace("\a", "").rstrip()
            m = _CPU.match(line)
            if m:
                self.cpu = m.group(1)
                continue
            if line.strip() == "Continue with SNePSLOG":
                continue
            if line == '"' and self.lines and self.lines[-1].startswith("Warning"):
                self.lines[-1] += '"'
                continue
            if line.startswith("Occurred in module"):
                line = "  (" + line + ")"
            if not line.strip():
                if not self.lines or not self.lines[-1].strip() or _ECHO.match(self.lines[-1]):
                    continue
            else:
                self.saw_output = True
            self.lines.append(line)
            if line.startswith("Warning:") and self.kb.dialect == "snepslog":
                self.parse_warning = True
        if len(self.lines) > 30000:
            del self.lines[:5000]

    def _on_waiting(self, snap: Snapshot) -> None:
        if self.question and not self.saw_output and snap.kind in TOP_LEVELS:
            self.lines.append(NO_ANSWER)
        if self.parse_warning:
            self.lines.append(PARSE_HINT)
            self.parse_warning = False
        self.question = False
        self.suppress = False
        self.snap = snap
        if snap.kind in TOP_LEVELS:
            self.kb = snap
            self._refresh_panel()
        if self.lines and self.lines[-1].strip():
            self.lines.append("")
        if snap.kind == "answer" and self.dialog is None:
            options = parse_menu(snap.recent)
            if options:
                title, text = self._question_text(snap.recent)
                self.choice_dialog(title, text, options, lambda opt: self.send(opt.answer),
                                   bottom=4)
                return
        self._send_pending()

    @staticmethod
    def _question_text(recent: list[str]) -> tuple[str, str]:
        """A title and a short summary of the question SNePS printed."""
        text = "\n".join(recent)
        start = text.rfind("=><=")
        block = [l.strip() for l in (text[start + 4:] if start >= 0 else text).split("\n")]

        def after(marker: str) -> str:
            for k, l in enumerate(block):
                if marker in l:
                    return next((x for x in block[k + 1:] if x), "")
            return ""
        if any("contradiction was detected" in l for l in block):
            new = after("you want to assert:") or after("newly derived proposition:")
            old = after("previously existing proposition:")
            return ("Contradiction", f"{new}\ncontradicts what SNePS already believes:\n{old}"
                    "\nWhat should SNePS do?")
        paragraphs, current = [], []
        for l in block + [""]:
            if l and not l.startswith(("1.", "2.", "3.", "4.", "(")) and not re.match(r"^\d+\s*:", l):
                current.append(l)
            elif current:
                paragraphs.append(" ".join(current))
                current = []
        if any("least like to keep" in p for p in paragraphs):
            return ("Which belief should SNePS give up?",
                    "SNePS must stop believing one of these hypotheses to remove the "
                    "contradiction. Pick the one you trust least:")
        for key in ("What do you want", "Do you want", "Please choose",
                    "that you are trying to build", "Enter the list number"):
            for p in paragraphs:
                if key in p:
                    return "SNePS asks", p
        return "SNePS asks", paragraphs[0] if paragraphs else "SNePS needs an answer."

    def _send_pending(self) -> None:
        while self.pending and not self.bridge.busy and self.dialog is None:
            line, kind = self.pending[0]
            if kind is not None and kind != self.snap.kind:
                return
            self.pending.popleft()
            self.send(line)

    # -- actions ----------------------------------------------------------------
    def say(self, text: str) -> None:
        """Show a short message above the input until the next event."""
        self.flash = text
        self.app.invalidate()

    def note(self, text: str) -> None:
        self.lines.append(text)
        self._refresh_transcript()

    def clear_transcript(self) -> None:
        """Empty the transcript; the knowledge base and the history stay."""
        self.lines.clear()
        self.follow = True
        self._refresh_transcript()
        self.say("Transcript cleared (the knowledge base is unchanged).")

    def send(self, line: str, echo: bool = True) -> None:
        """Give LINE to SNePS as if typed at the current prompt."""
        if echo:
            self.lines.append(f"{PROMPTS.get(self.snap.kind, '…')}❯ {line}")
        self.question = self.snap.kind == "snepslog" and line.rstrip().endswith("?")
        self.saw_output = False
        self.flash = None
        self.follow = True
        self.bridge.send(line)
        self._refresh_transcript()

    def submit(self) -> None:
        buf = self.input.buffer
        text = buf.text
        word = text.strip().lower()
        parts = word.split()
        if word == "?" or (parts and parts[0] in ("help", ":help") and len(parts) <= 2):
            buf.reset()
            if len(parts) == 2:
                topic = HELP_ALIASES.get(parts[1], parts[1])
                if topic not in [name for name, _, _ in HELP_TOPICS]:
                    self.toggle_help()
                    self.say(f"There is no help page {parts[1]}; the pages are "
                             + ", ".join(name for name, _, _ in HELP_TOPICS) + ".")
                    return
                self.toggle_help(topic)
            else:
                self.toggle_help()
            return
        if word in ("quit", "exit", ":q", ":quit"):
            buf.reset()
            self.quit_dialog()
            return
        if word in ("clear", "cls"):
            buf.reset()
            self.clear_transcript()
            return
        if self.bridge.finished:
            return
        if not word and self.snap.kind in TOP_LEVELS and not self.bridge.busy:
            buf.reset()
            return
        buf.append_to_history()
        if self.snap.kind in ("python", "escape", "pymore"):
            lines = text.split("\n")         # blank lines end Python blocks
        else:
            lines = [l for l in text.split("\n") if l.strip()] or [""]
        buf.reset()
        if self.bridge.busy:
            # type-ahead: sent in order once SNePS is ready again
            self.pending.extend((l, None) for l in lines)
            self.say(f"Queued {len(lines)} input{'s' if len(lines) > 1 else ''}; "
                     "it is sent when SNePS is ready (Ctrl+C interrupts).")
            return
        self.pending.extendleft(reversed([(l, None) for l in lines[1:]]))
        self.send(lines[0])

    def scroll(self, direction: int) -> None:
        buf = self.transcript.buffer
        rows = max(3, (self.transcript.window.render_info.window_height
                       if self.transcript.window.render_info else 20) - 2)
        doc = buf.document
        if direction < 0:
            buf.cursor_position += doc.get_cursor_up_position(count=rows)
        else:
            buf.cursor_position += doc.get_cursor_down_position(count=rows)
        self.follow = buf.cursor_position >= len(buf.text) - 1

    def _refresh_transcript(self) -> None:
        text = "\n".join(self.lines)
        buf = self.transcript.buffer
        pos = len(text) if self.follow else min(buf.cursor_position, len(text))
        buf.set_document(Document(text, cursor_position=pos), bypass_readonly=True)
        self.app.invalidate()

    def _refresh_panel(self) -> None:
        self.panel.buffer.set_document(Document(panel_text(self.kb), 0), bypass_readonly=True)

    def _idle_top_level(self) -> bool:
        if self.bridge.busy or self.snap.kind not in TOP_LEVELS:
            self.say("Finish the current input first (or press Ctrl+C).")
            return False
        return True

    def switch_to(self, target: str, then: Iterable[str] = ()) -> None:
        """Change the language of the session, then send THEN."""
        if not self._idle_top_level():
            return
        then = list(then)
        current = self.snap.kind
        if current == target:
            self.pending.extend((line, target) for line in then)
            self._send_pending()
            return
        self.bridge.next_mode = target
        exit_line = {"snepslog": "exit", "sneps": "(exit)", "python": SWITCH}[current]
        self.lines += [f"── now talking {MODE_NAMES[target]} ──", ""]
        self.pending.extend((line, target) for line in then)
        self.suppress = True
        self.send(exit_line, echo=False)

    def toggle_trace(self) -> None:
        if not self._idle_top_level():
            return
        on = not self.kb.trace
        net = self.net
        surface = self.kb.dialect == "snepslog"
        net.infertrace = ("surface" if surface else True) if on else None
        net.plantrace_mode = ("surface" if surface else True) if on else None
        self.kb.trace = on
        self.note("── tracing of reasoning is " + ("on: SNePS explains each step ──" if on else "off ──"))

    # -- dialogs -------------------------------------------------------------------
    def _open(self, body: Any, title: str, focus: Any, width: int = 84,
              bottom: Optional[int] = None) -> None:
        self.close_dialog(refocus=False)
        frame = Frame(body, title=title, style="class:dialog")
        self.dialog = Float(content=frame, width=lambda: min(width, self._columns() - 4),
                            bottom=bottom)
        self.floats.floats.insert(0, self.dialog)
        self.app.layout.focus(focus)
        self.app.invalidate()

    def close_dialog(self, refocus: bool = True) -> None:
        if self.dialog is not None:
            self.floats.floats.remove(self.dialog)
            self.dialog = None
        if refocus:
            self.app.layout.focus(self.input)
            self._send_pending()
        self.app.invalidate()

    def choice_dialog(self, title: str, text: str, options: list[Option],
                      on_choose: Callable[[Option], None], current: int = 0,
                      escape_hint: str = "Esc: type the answer yourself",
                      bottom: Optional[int] = None) -> None:
        def choose(opt: Option) -> None:
            self.close_dialog(refocus=True)
            on_choose(opt)
        choices = ChoiceList(options, choose, self.close_dialog, current)
        body = HSplit([
            Window(FormattedTextControl([("class:dialog.text", text)]), wrap_lines=True,
                   height=Dimension(min=1, max=6)),
            Window(height=1),
            choices.window,
            Window(FormattedTextControl([("class:dialog.dim",
                                          f"↑/↓ choose · Enter confirm · {escape_hint}")]),
                   height=1),
        ])
        self._open(body, title, choices.window, bottom=bottom)

    def input_dialog(self, title: str, text: str, default: str,
                     on_accept: Callable[[str], None]) -> None:
        field = TextArea(text=default, multiline=False)
        field.buffer.cursor_position = len(default)
        kb = KeyBindings()

        @kb.add("enter")
        def _ok(event: Any) -> None:
            value = field.text.strip()
            self.close_dialog()
            if value:
                on_accept(value)

        @kb.add("escape")
        def _cancel(event: Any) -> None:
            self.close_dialog()
        field.control.key_bindings = kb
        body = HSplit([Window(FormattedTextControl([("class:dialog.text", text)]), wrap_lines=True,
                              height=Dimension(min=1, max=4)),
                       Window(height=1), field, Window(height=1),
                       Window(FormattedTextControl([("class:dialog.dim",
                                                     "Enter confirm · Esc cancel")]), height=1)])
        self._open(body, title, field, width=72)

    def toggle_help(self, topic: Optional[str] = None) -> None:
        """Open the help at TOPIC (by default the page of the current mode),
        or close it if it is open and no TOPIC is given."""
        pages = getattr(self.dialog, "help", None) if self.dialog is not None else None
        if pages is not None:
            if topic is None:
                self.close_dialog()
            else:
                pages.show(pages.index_of(topic))
            return
        if topic is None:
            topic = help_topic(self.snap.kind, self.kb.dialect, self.kb.snepslog_mode)
        pages = HelpPages(self, topic)
        self._open(pages.body, pages.title, pages.view, width=HELP_WIDTH)
        self.dialog.height = lambda: max(8, get_app().output.get_size().rows - 4)
        self.dialog.is_help = True
        self.dialog.help = pages

    def mode_menu(self) -> None:
        if not self._idle_top_level():
            return
        options = [Option("snepslog1", "SNePSLOG: logic syntax, mode 1 (the usual choice)", "1"),
                   Option("snepslog2", "SNePSLOG mode 2: predicates become arc labels", "2"),
                   Option("snepslog3", "SNePSLOG mode 3: define your own case frames", "3"),
                   Option("sneps", "SNePSUL: the original SNePS command language", "s"),
                   Option("python", "Python: work with the knowledge base as `net`", "p")]
        kind = self.snap.kind
        current = {"sneps": 3, "python": 4}.get(kind, self.kb.snepslog_mode - 1)
        self.choice_dialog("Language and mode", "How do you want to talk to SNePS?", options,
                           self._choose_mode, current, "Esc: cancel")

    def _choose_mode(self, opt: Option) -> None:
        if not opt.answer.startswith("snepslog"):
            self.switch_to(opt.answer)
            return
        mode = int(opt.answer[-1])
        if self.snap.kind == "snepslog" and self.kb.snepslog_mode == mode:
            return
        if self.snap.kind != "snepslog" and self.kb.snepslog_mode == mode:
            self.switch_to("snepslog")
            return

        def confirmed(o: Option) -> None:
            if o.answer == "yes":
                self.switch_to("snepslog", [f"set-mode-{mode}"])
        self.choice_dialog("Change the SNePSLOG mode",
                           f"Changing to SNePSLOG mode {mode} clears the knowledge base.",
                           [Option("yes", f"Clear it and use mode {mode}", "y"),
                            Option("no", "Keep the knowledge base", "n")], confirmed, 1,
                           "Esc: cancel")

    def demo_menu(self) -> None:
        if not self._idle_top_level():
            return
        from ..snepslog.demos import SNEPSLOG_DEMOS, SNEPSUL_DEMOS
        options = [Option("snepslog:" + p, f"SNePSLOG · {label}", "") for p, label in SNEPSLOG_DEMOS]
        options += [Option("sneps:" + p, f"SNePSUL  · {label}", "") for p, label in SNEPSUL_DEMOS]

        def run(opt: Option) -> None:
            dialect, path = opt.answer.split(":", 1)
            target = f"sneps:demo;{path}"
            line = f'demo "{target}"' if dialect == "snepslog" else f'(demo "{target}")'
            self.switch_to(dialect, [line])
        self.choice_dialog("Demos", "Pick a demonstration; it runs in the transcript "
                           "(most demos start by clearing the knowledge base).",
                           options, run, 0, "Esc: cancel")

    def save_dialog(self) -> None:
        if not self._idle_top_level():
            return

        def save(path: str) -> None:
            from ..io import save_network
            try:
                save_network(self.net, os.path.expanduser(path))
            except Exception as e:
                self.note(f"Error: could not save {path}: {e}")
                return
            self.last_file = path
            fmt = "JSON" if path.lower().endswith(".json") else "SNePS network file"
            self.note(f"── saved the network to {path} ({fmt}) ──")
        self.input_dialog("Save the network", "File name. A name ending in .json saves JSON; "
                          "any other name uses the SNePS network file format.", self.last_file,
                          save)

    def open_dialog(self) -> None:
        if not self._idle_top_level():
            return

        def load(path: str) -> None:
            from ..io import load_network
            try:
                load_network(self.net, os.path.expanduser(path))
            except Exception as e:
                self.note(f"Error: could not open {path}: {e}")
                return
            self.last_file = path
            self.kb = self.bridge.snapshot(self.snap.kind, self.snap.prompt)
            self._refresh_panel()
            self.note(f"── loaded the network from {path} ──")
        self.input_dialog("Open a saved network", "File name (SNePS network file or JSON):",
                          self.last_file, load)

    def new_dialog(self) -> None:
        if not self._idle_top_level():
            return

        def clear(opt: Option) -> None:
            if opt.answer != "yes":
                return
            kind = self.snap.kind
            if kind == "snepslog":
                self.send("clearkb")
            elif kind == "sneps":
                self.send("(resetnet t)")
            else:
                self.net.resetnet(True)
                self.kb = self.bridge.snapshot(kind, self.snap.prompt)
                self._refresh_panel()
                self.note("── the knowledge base is empty ──")
        self.choice_dialog("Start over", "Remove everything SNePS knows?",
                           [Option("yes", "Yes, clear the knowledge base", "y"),
                            Option("no", "No", "n")], clear, 1, "Esc: cancel")

    def quit_dialog(self) -> None:
        def chosen(opt: Option) -> None:
            if opt.answer == "save":
                self.save_dialog_then_quit()
            elif opt.answer == "quit":
                self.quit()
        self.choice_dialog("Quit", "Leave PySNePS? The knowledge base is not saved "
                           "automatically.",
                           [Option("quit", "Quit", "q"), Option("save", "Save first, then quit", "s"),
                            Option("cancel", "Cancel", "c")], chosen, 0,
                           "Ctrl+Q again quits · Esc: cancel")
        self.dialog.is_quit = True

    def save_dialog_then_quit(self) -> None:
        def save(path: str) -> None:
            from ..io import save_network
            try:
                save_network(self.net, os.path.expanduser(path))
            except Exception as e:
                self.note(f"Error: could not save {path}: {e}")
                return
            self.quit()
        self.input_dialog("Save the network", "File name:", self.last_file, save)

    def quit(self) -> None:
        if self.exited:
            return
        self.bridge.stop()
        self.exited = True
        self.app.exit()


def run_tui(net: Any = None, mode: str = "snepslog", commands: Iterable[str] = (),
            welcome: bool = True) -> Any:
    """Start the full-screen interface; returns the network when it closes."""
    tui = SnepsTUI(net, mode, commands, welcome)
    tui.run()
    return tui.net


__all__ = ["SnepsTUI", "run_tui", "PYTHON_PROMPT"]
