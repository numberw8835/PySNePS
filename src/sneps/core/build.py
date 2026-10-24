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
"""Building and finding nodes (``sneps/fns/buildfns``, ``find``,
``findfilter``, ``findexact``).

A *cable set* is a list of ``(relation, node set)`` pairs describing the
arcs leaving a molecular node.  :meth:`BuildMixin.find_or_build` returns the
unique node with exactly that cable set, building it if needed, after
canonicalizing negations.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from .network import SNePSError
from .node import Node
from .nodeset import ns_compl, ns_insert, ns_intersect, ns_ismemb, ns_union

CableSet = list  # list of (relation, node set) pairs


def cs_get(cs: CableSet, r: str) -> Optional[tuple]:
    for rel, ns in cs:
        if rel == r:
            return ns
    return None


def cs_insert(cs: CableSet, r: str, ns: tuple) -> CableSet:
    """INSERT.CS: merge NS into the R cable of CS."""
    out = list(cs)
    for i, (rel, old) in enumerate(out):
        if rel == r:
            out[i] = (rel, ns_union(old, ns))
            return out
    out.append((r, ns))
    return out


class BuildMixin:
    # ------------------------------------------------------------------
    # build
    def find_or_build(self, cs: CableSet) -> tuple:
        """The node set containing the node with cable set CS (built if new)."""
        ccs = self.canonical_cs(cs)
        ns = self.findexact(ccs)
        return ns if ns else self.build1(ccs)

    def build1(self, cs: CableSet) -> tuple:
        if not cs:
            return ()
        return (self.buildpermnode(cs, self.getfreevars(cs)),)

    def getfreevars(self, cs: CableSet, buildperm: bool = True) -> tuple:
        freevars: tuple = ()
        bdvars: tuple = ()
        qflag = False
        for r, ns in cs:
            if self.isquant_r(r):
                if qflag:
                    raise SNePSError("Only 1 type of quantifier relation allowed ",
                                     "build" if buildperm else "tbuild", "getfreevars")
                bdvars = ns_union(bdvars, ns)
                freevars = ns_compl(freevars, bdvars)
                qflag = True
            else:
                for node in ns:
                    if node.is_var:
                        if not ns_ismemb(node, bdvars):
                            freevars = ns_insert(node, freevars)
                    elif node.is_pat:
                        freevars = ns_union(freevars, ns_compl(node.get_freevars(), bdvars))
        return freevars

    def buildpermnode(self, cs: CableSet, varnodes: tuple) -> Node:
        n = self.genppat() if varnodes else self.genpmol()
        n.fcableset = self.make_fcs(cs)
        n.height = self.calcheight(n)
        if n.is_pat:
            n.freevars = varnodes
        self.attachnode(n, cs)
        return n

    def attachnode(self, n: Node, cs: CableSet) -> Node:
        for r, ns in cs:
            conv = self.converse(r)
            for m in ns:
                self.updatenodeset(m, conv, n)
        return n

    # ------------------------------------------------------------------
    # canonical forms of negations
    def canonical_cs(self, cs: CableSet) -> CableSet:
        mx = cs_get(cs, "max")
        args = cs_get(cs, "arg")
        if mx and mx[0].to_number() == 0 and args is not None and len(args) == 1:
            return self.canonical_neg(args[0], cs)
        ants = cs_get(cs, "&ant")
        if (ants is not None and len(ants) == 1 and cs_get(cs, "emin") is None
                and cs_get(cs, "emax") is None):
            return [("ant" if r == "&ant" else r, ns) for r, ns in cs]
        return cs

    def _num(self, k: int) -> tuple:
        return (self.value_to_node(k),)

    def canonical_neg(self, p: Node, orig: CableSet) -> CableSet:
        if p.nodeset("forall"):
            return orig
        if p.is_and_or():
            args = p.nodeset("arg")
            mn = p.nodeset("min")[0].to_number()
            mx = p.nodeset("max")[0].to_number()
            tot = len(args)
            if p.is_not() and tot == 1:
                return self.n_to_downcs(args[0])
            if mn == 0:
                return [("min", self._num(mx + 1)), ("max", self._num(tot)), ("arg", args)]
            if mx == tot:
                return [("min", self._num(0)), ("max", self._num(mn - 1)), ("arg", args)]
            return [("thresh", p.nodeset("min")), ("threshmax", p.nodeset("max")),
                    ("arg", p.nodeset("arg"))]
        if p.is_thresh():
            mx = p.nodeset("threshmax") or self._num(len(p.nodeset("arg")) - 1)
            return [("min", p.nodeset("thresh")), ("max", mx), ("arg", p.nodeset("arg"))]
        return orig

    # ------------------------------------------------------------------
    # findexact
    def findexact(self, cs: CableSet) -> tuple:
        return self._findexact1(cs, sum(len(ns) for _r, ns in cs))

    def _count_wires_node(self, n: Node) -> int:
        return sum(len(ns) for _r, ns in self.down_fcs(n))

    def _cable_candidates(self, rel: Any, ns: tuple) -> tuple:
        pathform = rel if self.is_p(rel) else self.rel_to_path(rel)
        if len(pathform) == 1:
            return self.rel_to(rel, ns)
        return nbs_to_nodes(self.pathto(pathform, ns_to_nbs(ns)))

    def _findexact1(self, cs: CableSet, wirecount: int) -> tuple:
        if not cs:
            return ()
        rel, ns = cs[0]
        superset = tuple(n for n in self._cable_candidates(rel, ns)
                         if self._count_wires_node(n) >= wirecount)
        for rel, ns in cs[1:]:
            if not superset:
                break
            superset = ns_intersect(self._cable_candidates(rel, ns), superset)
        fcs = self.make_fcs(cs)
        for n in superset:
            if wirecount == self._count_wires_node(n) and self._fcs_equal(fcs, n):
                return (n,)
        return ()

    def _fcs_equal(self, fcs: dict, n: Node) -> bool:
        down = dict(self.down_fcs(n))
        if len(down) != len(fcs):
            return False
        for r, ns in fcs.items():
            other = down.get(r)
            if other is None or len(other) != len(ns) or any(a is not b for a, b in zip(ns, other)):
                return False
        return True

    def rel_to(self, r: str, ns: tuple) -> tuple:
        """The nodes with an R arc to every node of NS."""
        if not ns:
            return ns
        conv = self.converse(r)
        result = ns[0].nodeset(conv)
        for n in ns[1:]:
            result = ns_intersect(n.nodeset(conv), result)
            if not result:
                return ()
        return result

    # ------------------------------------------------------------------
    # negation
    def negate_n(self, n: Node) -> Node:
        """A node that is the negation of N."""
        zero = self._num(0)
        return self.find_or_build([("min", zero), ("max", zero), ("arg", (n,))])[0]

    def find_negate(self, n: Node) -> Optional[Node]:
        """The existing negation of N, if any."""
        zero = self.node("0")
        if zero is None:
            return None
        ccs = self.canonical_cs([("min", (zero,)), ("max", (zero,)), ("arg", (n,))])
        r = self.findexact(ccs)
        return r[0] if r else None

    def other_contradictory_nodes(self, p: Node) -> tuple:
        a = tuple(x for x in p.nodeset("arg-") if x.is_nor() and not x.is_not())
        b = p.nodeset("arg") if p.is_nor() else ()
        return ns_union(a, b)

    def contradictory_nodes(self, p: Node) -> tuple:
        notp = self.find_negate(p)
        if notp is not None:
            return ns_insert(notp, self.other_contradictory_nodes(p))
        return self.other_contradictory_nodes(p)

    # ------------------------------------------------------------------
    # building from Python
    def cables(self, pairs: Iterable[tuple]) -> CableSet:
        """The cable set of PAIRS, (relation, value) pairs in which a value
        is a node, a name or number (its base node, built if new), or a
        sequence of those (as in a SNePSUL ``build``)."""
        cs: CableSet = []
        for rel, value in pairs:
            ns = self._value_nodes(value)
            if ns:
                cs = cs_insert(cs, rel, ns)
        return cs

    def _value_nodes(self, value: Any) -> tuple:
        if value is None:
            return ()
        if isinstance(value, Node):
            return (value,)
        if isinstance(value, (list, tuple)):
            ns: tuple = ()
            for v in value:
                ns = ns_union(self._value_nodes(v), ns)
            return ns
        return (self.value_to_node(value),)

    def build(self, pairs: Iterable[tuple]) -> Node:
        """The molecular node with the cables PAIRS (see :meth:`cables`),
        built if it does not exist yet."""
        return self.find_or_build(self.cables(pairs))[0]

    def assert_built(self, pairs: Iterable[tuple], context: Any = None) -> tuple:
        """Build the node with the cables PAIRS and assert it in CONTEXT (the
        default context if None), as the SNePSUL ``assert`` command does;
        returns the asserted node set."""
        ct = context if context is not None else self.crntcontext(None)
        with self.let(crntct=ct):
            return self.assert_nodes(self.find_or_build(self.cables(pairs)), ct)

    # ------------------------------------------------------------------
    # assert
    def assert_nodes(self, ns: Iterable[Node], ctname: Any = None) -> tuple:
        """ASSERT-NODES: assert each molecular node of NS in context CTNAME."""
        if ctname is None:
            ctname = self.value_sv("defaultct")
        result: tuple = ()
        for n in ns:
            if not n.is_mol:
                raise SNePSError(f"cannot assert non-molecular node {n}", "assert", "assert")
            if self.assert_later > 0:
                self.new_propositions.insert(0, n)
            else:
                with self.let(crntct=ctname):
                    self.assert_n(n, ctname)
                self.sv_add("assertions", n)
            result = ns_insert(n, result)
        return result

    # ------------------------------------------------------------------
    # find
    def in_context_ns(self, ns: Iterable[Node], given: Any) -> list:
        """IN-CONTEXT.NS: the nodes of NS present in the current context.

        Unless a context was GIVEN, nodes without any support (non-asserted
        structure) are kept as well.
        """
        out = []
        for n in ns:
            if (not given and not n.asupport) or self.isassert(n) \
                    or any(self.isassert(m) for m in self.dominating_asupp_nodes(n)):
                out.append(n)
        return out

    def find_nbs(self, consts: list, qvars: list,
                 filt: Optional[Callable[[Node], bool]] = None) -> list:
        """FIND1 / FIND-FILTER.

        CONSTS is a list of ``(path, node-bind set)`` and QVARS a list of
        ``(path, variable-name)`` pairs.  Returns a node-bind set.
        """
        if not consts and not qvars:
            return []
        if consts:
            result = self._checkconsts(consts, filt)
            if result and qvars:
                return self._checkqvars(qvars, result)
            return result
        nodes = self.all_nodes()
        result = [(n, []) for n in nodes if filt is None or filt(n)]
        return self._checkqvars(qvars, result)

    def _checkconsts(self, consts: list, filt: Optional[Callable[[Node], bool]]) -> list:
        def get(c: tuple) -> list:
            nbs = self.pathto(c[0], c[1])
            if filt is not None:
                nbs = [nb for nb in nbs if filt(nb[0])]
            return nbs
        result = get(consts[0])
        for c in consts[1:]:
            if not result:
                return []
            result = intersect_nbs(get(c), result)
        return result

    def _checkqvars(self, qvars: list, result: list) -> list:
        out = []
        for n, bs in result:
            r = self._checkqvars1(n, bs, qvars)
            if r is not None:
                out.append(r)
        return out

    def _checkqvars1(self, n: Node, bs: list, qvars: list) -> Optional[tuple]:
        bs = list(bs)
        for path, sv in qvars:
            new = self.pathfrom(path, n)
            if not new:
                return None
            old = next((b[1] for b in bs if b[0] == sv), None)
            if not (not old or _ns_subset(new, old)):
                return None
            bs = replace_bs((sv, new), bs)
        return (n, bs)

    def nbs_to_ns(self, nbs: list) -> list:
        """NBS-TO-NS: set each variable bound in NBS and return the nodes."""
        for _n, bs in nbs:
            for var, _ns in bs:
                self.set_sv(var, ())
        for _n, bs in nbs:
            for var, ns in bs:
                cur = self.value_sv(var) or ()
                for m in ns:
                    cur = ns_insert(m, cur)
                self.set_sv(var, cur)
        return [nb[0] for nb in nbs]


def _ns_subset(a: tuple, b: tuple) -> bool:
    ids = {id(x) for x in b}
    return all(id(x) in ids for x in a)


def ns_to_nbs(ns: Iterable[Node]) -> list:
    return [(n, []) for n in ns]


def nbs_to_nodes(nbs: list) -> tuple:
    """The nodes of a node-bind set (as a sorted node set)."""
    out: tuple = ()
    for n, _bs in nbs:
        out = ns_insert(n, out)
    return out


def replace_bs(b: tuple, bs: list) -> list:
    """REPLACE.BS"""
    result = [b]
    for i, x in enumerate(bs):
        if x[0] == b[0]:
            return result + bs[i + 1:]
        result.insert(0, x)
    return result


def _intersect_bs(bs1: list, bs2: list) -> Any:
    if not bs1:
        return bs2
    if not bs2:
        return bs1
    result: list = []
    for var, ns1 in bs1:
        ns2 = next((x[1] for x in bs2 if x[0] == var), None)
        b = (var, ns1) if not ns2 else (var, ns_intersect(ns1, ns2))
        result.insert(0, b)
        if not b[1]:
            return "failure"
    return [b for b in bs2 if not any(x[0] == b[0] for x in result)] + result


def intersect_nbs(nbs1: list, nbs2: list) -> list:
    if not nbs1 or not nbs2:
        return []
    out = []
    for n1, bs1 in nbs1:
        for n2, bs2 in nbs2:
            if n1 is n2:
                r = _intersect_bs(bs1, bs2)
                if r != "failure":
                    out.append((n1, r))
    return out
