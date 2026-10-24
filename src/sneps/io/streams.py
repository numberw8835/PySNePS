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
"""Character streams for SNePS's input and output.

:class:`InputStream` reads characters and lines (with one character of
pushback) from a string, a file or an interactive line source, optionally
echoing what it consumes to an output stream, which is how a demo's input
appears in its transcript.  :class:`OutputStream` wraps a text sink and
tracks the output column, so that :meth:`~OutputStream.fresh_line` starts a
new line only when the current one is not empty.
"""

from __future__ import annotations

import io
import sys
from typing import Callable, Optional, TextIO


class OutputStream:
    """A text output stream that knows whether it is at the start of a line."""

    def __init__(self, sink: Optional[TextIO] = None):
        self.sink = sink if sink is not None else sys.stdout
        self.column = 0

    def write(self, s: str) -> None:
        if not s:
            return
        self.sink.write(s)
        nl = s.rfind("\n")
        if nl >= 0:
            self.column = len(s) - nl - 1
        else:
            self.column += len(s)

    def fresh_line(self) -> bool:
        if self.column != 0:
            self.write("\n")
            return True
        return False

    def terpri(self) -> None:
        self.write("\n")

    def flush(self) -> None:
        try:
            self.sink.flush()
        except Exception:
            pass

    def getvalue(self) -> str:
        return self.sink.getvalue()  # type: ignore[attr-defined]


class NullOutputStream(OutputStream):
    """Discards all output (like a broadcast stream with no components)."""

    def __init__(self):
        super().__init__(io.StringIO())

    def write(self, s: str) -> None:
        if not s:
            return
        nl = s.rfind("\n")
        if nl >= 0:
            self.column = len(s) - nl - 1
        else:
            self.column += len(s)


def string_output() -> OutputStream:
    return OutputStream(io.StringIO())


class InputStream:
    """Character input stream with one-character pushback and optional echo."""

    def __init__(self, text: Optional[str] = None,
                 line_source: Optional[Callable[[], Optional[str]]] = None,
                 name: Optional[str] = None,
                 echo: Optional[OutputStream] = None,
                 interactive: bool = False):
        self._buf = text or ""
        self._pos = 0
        self._line_source = line_source
        self._eof = line_source is None
        self.name = name
        self.echo = echo
        self._echoed_to = 0  # characters up to this position have been echoed
        self.interactive = interactive
        self.closed = False

    # -- construction helpers -------------------------------------------------
    @classmethod
    def from_file(cls, path: str, echo: Optional[OutputStream] = None) -> "InputStream":
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        return cls(text=text, name=path, echo=echo)

    @classmethod
    def from_textio(cls, f: TextIO, echo: Optional[OutputStream] = None,
                    interactive: bool = True) -> "InputStream":
        def src() -> Optional[str]:
            line = f.readline()
            return line if line else None
        return cls(line_source=src, name=getattr(f, "name", None), echo=echo,
                   interactive=interactive)

    # -- buffer management ----------------------------------------------------
    def _fill(self) -> bool:
        """Ensure at least one unread character is buffered; False at EOF."""
        while self._pos >= len(self._buf):
            if self._eof or self._line_source is None:
                return False
            line = self._line_source()
            if line is None:
                self._eof = True
                return False
            # discard the consumed prefix (keeping one character so that
            # unread_char always works) to keep the buffer small
            cut = self._pos - 1 if self._pos > 0 else 0
            self._buf = self._buf[cut:] + line
            self._echoed_to = max(0, self._echoed_to - cut)
            self._pos -= cut
        return True

    def _echo_upto(self, pos: int) -> None:
        if self.echo is not None and pos > self._echoed_to:
            self.echo.write(self._buf[self._echoed_to:pos])
        if pos > self._echoed_to:
            self._echoed_to = pos

    # -- reading -------------------------------------------------------------------
    def read_char(self) -> Optional[str]:
        if not self._fill():
            return None
        ch = self._buf[self._pos]
        self._pos += 1
        self._echo_upto(self._pos)
        return ch

    def peek_char(self) -> Optional[str]:
        if not self._fill():
            return None
        return self._buf[self._pos]

    def unread_char(self, ch: Optional[str] = None) -> None:
        if self._pos > 0:
            self._pos -= 1

    def at_eof(self) -> bool:
        return not self._fill()

    def read_line(self) -> tuple[Optional[str], bool]:
        """Return (line-without-newline, missing-newline-p); line is None at EOF."""
        if not self._fill():
            return None, True
        out = []
        while True:
            if not self._fill():
                self._echo_upto(self._pos)
                return "".join(out), True
            nl = self._buf.find("\n", self._pos)
            if nl < 0:
                out.append(self._buf[self._pos:])
                self._pos = len(self._buf)
                self._echo_upto(self._pos)
                continue
            out.append(self._buf[self._pos:nl])
            self._pos = nl + 1
            self._echo_upto(self._pos)
            return "".join(out), False

    def remaining_text(self) -> str:
        """Consume and return everything left (only for finite streams)."""
        parts = []
        while self._fill():
            parts.append(self._buf[self._pos:])
            self._pos = len(self._buf)
            self._echo_upto(self._pos)
        return "".join(parts)

    def close(self) -> None:
        self.closed = True


def string_input(text: str, echo: Optional[OutputStream] = None) -> InputStream:
    return InputStream(text=text, echo=echo)


class ConcatenatedInputStream(InputStream):
    """Reads from several input streams in sequence."""

    def __init__(self, *streams: InputStream):
        self._streams = list(streams)
        super().__init__(line_source=self._next_line)
        self.echo = None

    def _next_line(self) -> Optional[str]:
        while self._streams:
            s = self._streams[0]
            line, missing = s.read_line()
            if line is None:
                self._streams.pop(0)
                continue
            return line if missing else line + "\n"
        return None
