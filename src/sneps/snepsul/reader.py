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
"""Reading SNePSUL expressions.

The reader turns SNePSUL text into plain Python data: ``(a b)`` becomes a
list, names become ``str``, ``"..."`` a :class:`~sneps.core.printing.Text`,
numbers numbers, ``nil`` ``None`` and ``t`` ``True``.  Names may be escaped
with ``\\`` and ``|...|``; ``;`` starts a comment, ``#| ... |#`` encloses one.

In SNePSUL syntax (``macros=True``) these characters are abbreviations:
``*x`` is ``(* x)`` (the value of a SNePS variable), ``$x`` ``($ x)`` (a new
variable node), ``#x`` ``(# x)`` (a new base node), ``?x`` ``(? x)`` (a
``find`` variable), ``%x`` ``(% x)``, and ``!`` and ``=`` stand alone; they
also end the name before them.  ``'x`` is ``(quote x)``.

``^`` escapes to Python: ``^(expr)`` is a parenthesised Python expression,
``(^ expr)`` takes the rest of the list as Python, and at top level ``^``
takes the rest of the line.  The result is ``["^", PythonCode(source)]``.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, Optional

from ..core.printing import Text
from ..io.streams import InputStream


class ReaderError(Exception):
    pass


class _EOF:
    def __repr__(self) -> str:
        return "#<end of input>"


EOF = _EOF()

WHITESPACE = frozenset(" \t\n\r\f\v")
_TERMINATING = frozenset("()'\";`,")
_MACRO_CHARS = frozenset("*$%#?!=")
_ABBREVIATIONS = {"*": "*", "$": "$", "%": "%", "?": "?", "#": "#"}

_INT_RE = re.compile(r"^[+-]?[0-9]+\.?$")
_RATIO_RE = re.compile(r"^[+-]?[0-9]+/[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:[0-9]*\.[0-9]+(?:[esfdlESFDL][+-]?[0-9]+)?"
    r"|[0-9]+(?:\.[0-9]*)?[esfdlESFDL][+-]?[0-9]+)$")


class PythonCode:
    """Python source read after ``^``."""

    __slots__ = ("source",)

    def __init__(self, source: str):
        self.source = source

    def __repr__(self) -> str:
        return self.source

    __str__ = __repr__


def parse_token(text: str, escaped: list[bool], had_escape: bool,
                fold_case: Optional[str]) -> Any:
    """The datum a token denotes: a number, None, True or a name."""
    if not had_escape:
        if _INT_RE.match(text):
            return int(text.rstrip("."))
        if _RATIO_RE.match(text):
            num, den = text.split("/")
            fr = Fraction(int(num), int(den))
            return fr.numerator if fr.denominator == 1 else fr
        if _FLOAT_RE.match(text):
            return float(re.sub(r"[sfdlSFDL]", "e", text))
        low = text.lower()
        if low == "nil":
            return None
        if low == "t":
            return True
    if fold_case:
        fold = str.lower if fold_case == "lower" else str.upper
        text = "".join(ch if e else fold(ch) for ch, e in zip(text, escaped))
    return text


class SnepsulReader:
    """Reads SNePSUL expressions from an :class:`~sneps.io.streams.InputStream`."""

    def __init__(self, stream: InputStream, fold_case: Optional[str] = None,
                 macros: bool = True, extra_terminating: str = ""):
        self.stream = stream
        self.fold_case = fold_case
        self.macros = macros
        self.terminating = _TERMINATING | (_MACRO_CHARS if macros else frozenset()) \
            | frozenset(extra_terminating)

    # ------------------------------------------------------------------
    def read(self) -> Any:
        """The next expression, or EOF at the end of the input."""
        return self._read(depth=0)

    def _skip(self) -> Optional[str]:
        """Skip whitespace and comments; the next character (not consumed)."""
        s = self.stream
        while True:
            c = s.peek_char()
            if c is None:
                return None
            if c in WHITESPACE:
                s.read_char()
            elif c == ";":
                while c is not None and c != "\n":
                    c = s.read_char()
            elif c == "#" and self._block_comment():
                continue
            else:
                return c

    def _block_comment(self) -> bool:
        """Skip a ``#| ... |#`` comment if one starts here."""
        s = self.stream
        s.read_char()
        if s.peek_char() != "|":
            s.unread_char()
            return False
        s.read_char()
        depth, prev = 1, ""
        while depth:
            c = s.read_char()
            if c is None:
                raise ReaderError("end of input inside #| ... |#")
            if prev == "|" and c == "#":
                depth, prev = depth - 1, ""
            elif prev == "#" and c == "|":
                depth, prev = depth + 1, ""
            else:
                prev = c
        return True

    def _read(self, depth: int) -> Any:
        c = self._skip()
        if c is None:
            return EOF
        s = self.stream
        s.read_char()
        if c == "(":
            return self._read_list(depth + 1)
        if c == ")":
            raise ReaderError("unmatched close parenthesis")
        if c == "'":
            return ["quote", self._required(depth)]
        if c == '"':
            return self._read_string()
        if c in "`,":
            raise ReaderError(f"unexpected {c}")
        if self.macros and c in _MACRO_CHARS:
            if c in "!=":
                return c
            if c == "#" and s.peek_char() == "#":
                raise ReaderError("unexpected ##")
            return [_ABBREVIATIONS[c], self._required(depth)]
        if c == "^" and self.macros:
            return self._read_caret(depth)
        s.unread_char()
        return self._read_token()

    def _required(self, depth: int) -> Any:
        obj = self._read(depth)
        if obj is EOF:
            raise ReaderError("end of input")
        return obj

    def _read_list(self, depth: int) -> list:
        items: list = []
        while True:
            c = self._skip()
            if c is None:
                raise ReaderError("end of input inside a list")
            if c == ")":
                self.stream.read_char()
                return items
            if c == "^" and self.macros and self._standalone_caret():
                # (^ python ...): the rest of the list is Python source
                self.stream.read_char()
                items += ["^", PythonCode(self._python_until_close())]
                self.stream.read_char()
                return items
            items.append(self._read(depth))

    def _read_string(self) -> Text:
        s = self.stream
        out = []
        while True:
            c = s.read_char()
            if c is None:
                raise ReaderError("end of input inside a string")
            if c == "\\":
                c = s.read_char()
                if c is None:
                    raise ReaderError("end of input inside a string")
                out.append(c)
            elif c == '"':
                return Text("".join(out))
            else:
                out.append(c)

    def read_raw_token(self) -> tuple[str, list[bool], bool]:
        """The characters of the next token, which of them were escaped, and
        whether there was any escape."""
        s = self.stream
        chars: list[str] = []
        escaped: list[bool] = []
        had_escape = False
        while True:
            c = s.read_char()
            if c is None:
                break
            if c == "\\":
                c2 = s.read_char()
                if c2 is None:
                    raise ReaderError("end of input after \\")
                chars.append(c2)
                escaped.append(True)
                had_escape = True
            elif c == "|":
                had_escape = True
                while True:
                    c2 = s.read_char()
                    if c2 is None:
                        raise ReaderError("end of input inside |...|")
                    if c2 == "|":
                        break
                    if c2 == "\\":
                        c2 = s.read_char()
                        if c2 is None:
                            raise ReaderError("end of input inside |...|")
                    chars.append(c2)
                    escaped.append(True)
            elif c in WHITESPACE:
                break
            elif c in self.terminating:
                s.unread_char()
                break
            else:
                chars.append(c)
                escaped.append(False)
        return "".join(chars), escaped, had_escape

    def _read_token(self) -> Any:
        text, escaped, had_escape = self.read_raw_token()
        if text == "." and not had_escape:
            raise ReaderError("a lone dot is not a SNePSUL expression")
        return parse_token(text, escaped, had_escape, self.fold_case)

    # ------------------------------------------------------------------
    # Python escapes
    def _standalone_caret(self) -> bool:
        """At a ``^`` that is followed by whitespace."""
        s = self.stream
        s.read_char()
        nxt = s.peek_char()
        s.unread_char()
        return nxt is None or nxt in WHITESPACE

    def _read_caret(self, depth: int) -> Any:
        s = self.stream
        nxt = s.peek_char()
        if nxt == "^":
            s.read_char()
            return "^^"
        if nxt == "(":
            return ["^", PythonCode(self._python_balanced())]
        if depth == 0:
            line, _ = s.read_line()
            while line is not None and not line.strip():
                line, _ = s.read_line()
            return ["^", PythonCode((line or "").strip())]
        # ^name inside a list: the name is a Python expression
        text, _, _ = self.read_raw_token()
        return ["^", PythonCode(text)]

    def _python_balanced(self) -> str:
        """A parenthesised Python expression, starting at its ``(``."""
        s = self.stream
        out = [s.read_char()]
        out.append(self._python_until_close())
        out.append(s.read_char() or "")
        return "".join(out)

    def _python_until_close(self) -> str:
        """Python source up to (not including) the ``)`` that closes the
        enclosing parenthesis; strings and comments are skipped over."""
        s = self.stream
        out: list[str] = []
        depth = 0
        while True:
            c = s.peek_char()
            if c is None:
                raise ReaderError("end of input inside a Python escape")
            if c in ")]}" and depth == 0:
                if c != ")":
                    raise ReaderError(f"unbalanced {c} in a Python escape")
                return "".join(out).strip()
            s.read_char()
            out.append(c)
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth -= 1
            elif c in "'\"":
                out.append(self._python_string_rest(c))
            elif c == "#":
                while s.peek_char() not in (None, "\n"):
                    out.append(s.read_char())

    def _python_string_rest(self, quote: str) -> str:
        """The rest of a Python string literal whose opening QUOTE was read."""
        s = self.stream
        if s.peek_char() == quote:
            s.read_char()
            if s.peek_char() != quote:
                return quote                    # an empty string
            s.read_char()
            prefix, end = quote * 2, quote * 3
        else:
            prefix, end = "", quote
        body: list[str] = []
        while True:
            c = s.read_char()
            if c is None:
                raise ReaderError("end of input inside a Python string")
            body.append(c)
            if c == "\\":
                body.append(s.read_char() or "")
            elif c == quote and "".join(body[-len(end):]) == end:
                return prefix + "".join(body)

def read_from_string(text: str, fold_case: Optional[str] = None,
                     macros: bool = False) -> tuple[Any, int]:
    """The first expression in TEXT and the index just after it."""
    stream = InputStream(text=text)
    obj = SnepsulReader(stream, fold_case, macros).read()
    return obj, stream._pos


def read_all(text: str, fold_case: Optional[str] = None, macros: bool = True) -> list:
    """Every expression in TEXT."""
    reader = SnepsulReader(InputStream(text=text), fold_case, macros)
    out = []
    while True:
        obj = reader.read()
        if obj is EOF:
            return out
        out.append(obj)
