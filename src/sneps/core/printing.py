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
"""How SNePS writes its data: node names, SNePSUL expressions and node
descriptions.

SNePSUL data is plain Python: names are ``str``, string literals are
:class:`Text`, numbers are numbers, ``None`` is ``nil``, ``True`` is ``t``,
lists and tuples are parenthesised, and nodes print as their names.

With ``escape=True`` the text can be read back by the SNePSUL reader: names
that would read as something else are written between bars (``|0|``,
``|police officer|``) and string literals in double quotes.  The pretty
printer breaks lines fill-style within a right margin of 79 columns,
indenting continuation lines one column past the opening parenthesis, which
is how ``describe`` output is laid out.
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import Any, NamedTuple

RIGHT_MARGIN = 79


class Text(str):
    """A string literal (``"..."``), as opposed to a name."""

    __slots__ = ()


class Binding(NamedTuple):
    """A variable binding returned by ``deducewh``; prints as ``(var . value)``."""

    var: Any
    value: Any


_NUMBERISH = re.compile(r"^[+-]?(?:[0-9]+\.?|[0-9]*\.[0-9]+(?:[esfdlESFDL][+-]?[0-9]+)?"
                        r"|[0-9]+(?:\.[0-9]*)?[esfdlESFDL][+-]?[0-9]+|[0-9]+/[0-9]+)$")
_NEEDS_BARS = set(" \t\n\r\f()'\";`,|\\")


def name_needs_bars(name: str) -> bool:
    """True if NAME would not read back as the same name."""
    if name == "" or name == ".":
        return True
    if any(c in _NEEDS_BARS for c in name) or ":" in name:
        return True
    return bool(_NUMBERISH.match(name))


def escape_name(name: str) -> str:
    """NAME as written in SNePSUL: between bars if it needs them."""
    if name_needs_bars(name):
        return "|" + name.replace("\\", "\\\\").replace("|", "\\|") + "|"
    return name


def number_text(x: Any) -> str:
    if isinstance(x, Fraction):
        return f"{x.numerator}/{x.denominator}"
    return repr(x) if isinstance(x, float) else str(x)


def atom_text(obj: Any, escape: bool) -> str:
    if obj is None or obj is False:
        return "nil"
    if obj is True:
        return "t"
    if isinstance(obj, Text):
        return '"' + obj.replace("\\", "\\\\").replace('"', '\\"') + '"' if escape else str(obj)
    if isinstance(obj, str):
        if escape and not obj.startswith(":"):
            return escape_name(obj)
        return obj
    if isinstance(obj, (int, float, Fraction)):
        return number_text(obj)
    if callable(obj) and not hasattr(obj, "fcableset"):
        return f"#<function {getattr(obj, '__name__', 'anonymous')}>"
    return str(obj)


def _is_list(obj: Any) -> bool:
    return isinstance(obj, (list, tuple)) and len(obj) > 0 and not isinstance(obj, Binding)


_ABBREVIATED = {"quote": "'", "$": "$", "*": "*", "#": "#", "?": "?", "%": "%"}


def _quote_prefix(obj: Any) -> str:
    """The SNePSUL abbreviation of OBJ (``'x``, ``$x``, ``*x`` ...), if any."""
    if isinstance(obj, list) and len(obj) == 2 and type(obj[0]) is str \
            and not isinstance(obj[1], list):
        return _ABBREVIATED.get(obj[0], "")
    if isinstance(obj, list) and len(obj) == 2 and obj[0] == "quote" and type(obj[0]) is str:
        return "'"
    return ""


def flat_text(obj: Any, escape: bool = False) -> str:
    """OBJ on one line."""
    if isinstance(obj, Binding):
        return f"({flat_text(obj.var, escape)} . {flat_text(obj.value, escape)})"
    if not _is_list(obj):
        if isinstance(obj, (list, tuple)):
            return "nil"
        return atom_text(obj, escape)
    q = _quote_prefix(obj)
    if q:
        return q + flat_text(obj[1], escape)
    return "(" + " ".join(flat_text(x, escape) for x in obj) + ")"


def pretty_text(obj: Any, escape: bool = False, column: int = 0,
                margin: int = RIGHT_MARGIN) -> str:
    """OBJ with fill-style line breaks, starting at COLUMN."""
    out: list[str] = []
    _render(obj, column, 0, escape, margin, out)
    return "".join(out)


def _render(obj: Any, col: int, after: int, escape: bool, margin: int,
            out: list[str]) -> tuple[int, bool]:
    """Append OBJ to OUT; return (end column, rendered on several lines)."""
    flat = flat_text(obj, escape)
    if not _is_list(obj) or col + len(flat) + after <= margin:
        out.append(flat)
        return col + len(flat), False
    q = _quote_prefix(obj)
    if q:
        out.append(q)
        return _render(obj[1], col + len(q), after, escape, margin, out)
    items = list(obj)
    indent = col + 1
    out.append("(")
    n = len(items)
    c, multi = _render(items[0], indent, (1 + after) if n == 1 else 0, escape, margin, out)
    any_multi = multi
    for i in range(1, n):
        e = items[i]
        e_after = (1 + after) if i == n - 1 else 0
        section = 1 + len(flat_text(e, escape)) + e_after
        if multi or c + section > margin:
            out.append("\n" + " " * indent)
            c = indent
            any_multi = True
        else:
            out.append(" ")
            c += 1
        c, multi = _render(e, c, e_after, escape, margin, out)
        any_multi = any_multi or multi
    out.append(")")
    return c + 1, any_multi
