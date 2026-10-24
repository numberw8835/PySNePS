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
"""SNePS nodes (``sneps/ds/node0``, ``node1``, ``node2``).

A node has a name, a type (``base``, ``mol``, ``var`` or ``pat``), a creation
order, and a flat cable set mapping each relation to a node set.  Molecular,
pattern and variable nodes are generated with names ``M1``, ``P1``, ``V1``;
base nodes are usually named by the user (``B1``... when generated).
"""

from __future__ import annotations

import re
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .network import Network

BASE = "base"
MOL = "mol"
VAR = "var"
PAT = "pat"

_INT_RE = re.compile(r"^[+-]?[0-9]+$")
_RATIO_RE = re.compile(r"^[+-]?[0-9]+/[0-9]+$")
_FLOAT_RE = re.compile(
    r"^[+-]?(?:[0-9]*\.[0-9]+(?:[eEdD][+-]?[0-9]+)?|[0-9]+(?:\.[0-9]*)?[eEdD][+-]?[0-9]+)$")


def number_name(x: Any) -> str:
    """The name of the node that stands for the number X."""
    if isinstance(x, bool):
        return "T" if x else "NIL"
    if isinstance(x, Fraction):
        return f"{x.numerator}/{x.denominator}"
    if isinstance(x, float):
        r = repr(x)
        return r
    return str(x)


def parse_number(name: str) -> Optional[Any]:
    """The number named by NAME if it prints back identically, else None."""
    if _INT_RE.match(name):
        v = int(name)
        return v if str(v) == name else None
    if _RATIO_RE.match(name):
        num, den = name.split("/")
        fr = Fraction(int(num), int(den))
        if fr.denominator == 1:
            return None
        return fr if number_name(fr) == name else None
    if _FLOAT_RE.match(name):
        try:
            v = float(name.replace("d", "e").replace("D", "e"))
        except ValueError:
            return None
        return v if number_name(v) == name else None
    return None


class Node:
    """A SNePS node."""

    __slots__ = ("name", "order", "type", "perm", "height", "freevars", "fcableset",
                 "activation", "asupport", "jsupport", "contexts", "snepslog",
                 "net", "__weakref__")

    def __init__(self, name: str, type: str, order: int, perm: bool = False,
                 net: Optional["Network"] = None):
        self.name = name
        self.order = order
        self.type = type
        self.perm = perm
        self.height = 0
        self.freevars: tuple = ()
        self.fcableset: dict = {}   # relation name -> node set, in relation order
        self.activation = None      # SNIP process
        self.asupport: tuple = ()   # context cable set
        self.jsupport = None
        self.contexts: tuple = ()   # contexts in which this node is a hypothesis
        self.snepslog = None        # cached SNePSLOG rendering / variable name
        self.net = net

    # -- printing ------------------------------------------------------------
    def __repr__(self) -> str:
        """The node as SNePS prints it: its name (between bars when it needs
        them, e.g. ``|2|``), followed by ``!`` if asserted."""
        from .printing import escape_name
        s = escape_name(self.name)
        if self.net is not None and self.net.isassert(self):
            return s + "!"
        return s

    __str__ = __repr__

    # -- type predicates -----------------------------------------------------
    @property
    def is_base(self) -> bool:
        return self.type == BASE

    @property
    def is_mol(self) -> bool:
        return self.type == MOL

    @property
    def is_var(self) -> bool:
        return self.type == VAR

    @property
    def is_pat(self) -> bool:
        return self.type == PAT

    # -- cables --------------------------------------------------------------
    def nodeset(self, r: str) -> tuple:
        """NODESET.N: the nodes related to this node by relation R."""
        return self.fcableset.get(r, ())

    def get_freevars(self) -> tuple:
        """FREEVARS.N"""
        if self.freevars:
            return self.freevars
        if self.type == VAR:
            return (self,)
        return ()

    @property
    def value(self) -> Any:
        """The node's name as a value: a number if the name reads as one."""
        v = parse_number(self.name)
        return self.name if v is None else v

    def is_number(self) -> bool:
        return parse_number(self.name) is not None

    def to_number(self) -> Any:
        v = parse_number(self.name)
        if v is None:
            raise ValueError(f"Non-number node passed to node-to-number.n: {self.name}")
        return v

    # -- rule-type predicates (node2) -----------------------------------
    def quantified_vars(self) -> tuple:
        for r in ("forall", "exists", "vars", "pevb"):
            ns = self.nodeset(r)
            if ns:
                return ns
        return ()

    def quantifier_of(self) -> Optional[str]:
        for r in ("forall", "exists", "vars", "pevb"):
            if self.nodeset(r + "-"):
                return r
        return None

    def is_v_ent(self) -> bool:
        return bool(self.nodeset("ant"))

    def is_and_ent(self) -> bool:
        return bool(self.nodeset("&ant")) and not self.nodeset("thresh") and not self.nodeset("pevb")

    def is_thresh(self) -> bool:
        return bool(self.nodeset("thresh")) and bool(self.nodeset("arg"))

    def is_and_or(self) -> bool:
        return bool(self.nodeset("min"))

    def is_nor(self) -> bool:
        mx = self.nodeset("max")
        return bool(mx) and mx[0].to_number() == 0

    def is_and(self) -> bool:
        mn = self.nodeset("min")
        tot = len(self.nodeset("arg"))
        return bool(mn) and bool(tot) and mn[0].to_number() == tot

    def is_not(self) -> bool:
        return self.is_nor() and len(self.nodeset("arg")) == 1

    def is_num_ent(self) -> bool:
        return bool(self.nodeset("thresh")) and bool(self.nodeset("&ant"))

    def is_num_quant(self) -> bool:
        return bool(self.nodeset("pevb"))

    def is_non_deriv(self) -> bool:
        return bool(self.nodeset("i-//-"))

    def is_rule(self) -> bool:
        return (self.is_v_ent() or self.is_and_ent() or self.is_and_or()
                or self.is_thresh() or self.is_num_ent() or self.is_num_quant())

    def is_act(self) -> bool:
        return bool(self.nodeset("action"))

    def is_do_if(self) -> bool:
        return bool(self.nodeset("if"))

    def is_when_do(self) -> bool:
        return bool(self.nodeset("when"))

    def is_whenever_do(self) -> bool:
        return bool(self.nodeset("whenever"))


def symbol_type(name: str) -> str:
    """SYMBOL-TYPE.N: the node type suggested by a node name."""
    if len(name) >= 2 and name[0] in "MPV" and name[1:].isdigit():
        return {"M": MOL, "P": PAT, "V": VAR}[name[0]]
    return BASE
