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
"""Unification and matching of SNePS nodes (``match/``).

This implements the unification algorithm with the unique variable binding
rule (UVBR) used by SNIP: :meth:`MatchMixin.match` finds the nodes that
unify with a pattern, returning matchings ``[node, source-sub, target-sub]``.

Substitutions handed to SNIP are tuples of ``(variable, term)`` pairs.
Internally, unification works on association lists of mutable
``[variable, value]`` cells, because the algorithm relies on bindings being
updated in place across shared lists exactly as in SNePS 2.8.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from ..core.node import Node
from ..core.nodeset import ns_insert, ns_ismemb, ns_union
from ..core.paths import UNBOUND
from ..core.build import cs_insert

LOOP = "loop"
DONE = "done"

_NO_NUMBER_RELS = ("min", "max", "thresh", "threshmax", "emin", "emax", "etot")


class UnifyTrap(Exception):
    """Raised when unification fails."""


def _uvbr(x: Any) -> bool:
    return isinstance(x, tuple) and len(x) == 2 and x[0] == "uvbr"


# -- association lists of mutable cells -------------------------------------

def aget(al: list, k: Any) -> Any:
    for p in al:
        if p[0] is k:
            return p[1]
    return None


def aset(al: list, k: Any, v: Any) -> list:
    """(SETF (CDR (ASSOC K AL)) V): mutate the cell or push a new one."""
    for p in al:
        if p[0] is k:
            p[1] = v
            return al
    return [[k, v]] + al


def ahas(al: list, k: Any) -> bool:
    return any(p[0] is k for p in al)


def arassoc(al: list, v: Any) -> bool:
    return any(p[1] is v for p in al)


def copy_alist(al: Optional[Iterable]) -> list:
    return [[p[0], p[1]] for p in (al or ())]


# -- substitutions (tuples of (var, term) pairs) ------------------------------

def binding_of(v: Node, sbst: Iterable) -> Optional[Node]:
    for p in sbst or ():
        if p[0] is v:
            return p[1]
    return None


def initbind(pat: Node) -> tuple:
    return tuple((v, v) for v in pat.get_freevars())


def restrict_binding_to_pat(bndg: Iterable, pat: Node) -> tuple:
    fv = pat.get_freevars()
    return tuple(p for p in bndg if ns_ismemb(p[0], fv))


def uvbr_conflict(sub1: Iterable, sub2: Iterable) -> bool:
    sub2 = tuple(sub2)
    for v1, t1 in sub1:
        v2 = next((p[0] for p in sub2 if p[1] is t1), None)
        if v2 is not None and v2 is not v1:
            return True
    return False


def violates_uvbr(sub: Iterable) -> bool:
    sub = tuple(sub)
    for i in range(len(sub) - 1):
        v = sub[i][1]
        if any(p[1] is v for p in sub[i + 1:]):
            return True
    return False


class MatchMixin:
    """Unification and matching, mixed into :class:`~sneps.Network`."""

    # ------------------------------------------------------------------
    def _rulep(self, t: Node) -> bool:
        return (t.is_and_or() or t.is_and_ent() or t.is_v_ent() or t.is_thresh()
                or t.is_num_ent() or t.is_non_deriv() or t.is_num_quant())

    def _here(self, t1: Any, t2: Any, r1: list, r2: list, init1: Any, init2: Any,
              t2istarget: bool) -> list:
        if not (isinstance(t1, Node) and isinstance(t2, Node)):
            raise UnifyTrap
        if t1 is t2 and (t1.is_base or t1.is_mol):
            return [[r1, r2] if t2istarget else [r2, r1]]
        if t1.is_base and t2.is_base:
            raise UnifyTrap
        if t1.is_var:
            return self._var_here(t1, t2, r1, r2, init1, init2, t2istarget)
        if t2.is_var:
            return self._var_here(t2, t1, r2, r1, init2, init1, not t2istarget)
        if t1.is_base or t2.is_base:
            raise UnifyTrap
        if t2istarget:
            return self._pat_here(t1, t2, r1, r2, init1, init2)
        return self._pat_here(t2, t1, r2, r1, init2, init1)

    def _downfcs_pbi(self, tnode: Node, downrels: list) -> dict:
        result: dict = {}
        for rel in downrels:
            ns = self.pathfrom(self.checkpath(rel), tnode)
            if ns:
                result[rel] = ns if rel not in result else ns_union(result[rel], ns)
        return result

    def _pat_here(self, snode: Node, tnode: Node, rs: list, rt: list, inits: Any,
                  initt: Any) -> list:
        self._checkrulecompatability(snode, tnode)
        t_fcs = self.down_fcs(tnode)
        s_fcs = self._downfcs_pbi(snode, [r for r, _ns in reversed(t_fcs)])
        tnss: list = []
        snss: list = []
        for ri, trmi in t_fcs:
            if ri not in _NO_NUMBER_RELS:
                tnss.insert(0, trmi)
                snss.insert(0, s_fcs.get(ri, ()))
        return self._unifynss(tnss, snss, rt, rs, initt, inits)

    def _checkrulecompatability(self, s: Node, t: Node) -> None:
        def num(n: Node, r: str) -> Any:
            return n.nodeset(r)[0].to_number()

        def card(n: Node, r: str) -> int:
            return len(n.nodeset(r))
        if s.is_and_or():
            ok = False
            if t.is_and_or():
                ti, tj, tn = num(t, "min"), num(t, "max"), card(t, "arg")
                si, sj, sn = num(s, "min"), num(s, "max"), card(s, "arg")
                ok = tn <= sn and ti == max(si - (sn - tn), 0) and tj == sj
            if not ok:
                raise UnifyTrap
        elif s.is_and_ent():
            if not (t.is_and_ent() and card(t, "&ant") == card(s, "&ant")
                    and card(t, "cq") <= card(s, "cq") and card(t, "dcq") <= card(s, "dcq")):
                raise UnifyTrap
        elif s.is_v_ent():
            if not (t.is_v_ent() and card(t, "ant") == card(s, "ant")
                    and card(t, "cq") <= card(s, "cq") and card(t, "dcq") <= card(s, "dcq")):
                raise UnifyTrap
        elif s.is_thresh():
            ok = False
            if t.is_thresh():
                ti = num(t, "thresh")
                tj = num(t, "threshmax") if t.nodeset("threshmax") else card(t, "arg") - 1
                tn = card(t, "arg")
                si = num(s, "thresh")
                sj = num(s, "threshmax") if s.nodeset("threshmax") else card(s, "arg") - 1
                sn = card(s, "arg")
                ok = tn <= sn and ti == max(si - (sn - tn), 0) and tj == sj
            if not ok:
                raise UnifyTrap
        elif s.is_num_ent():
            if not (t.is_and_ent() and card(t, "&ant") == card(s, "&ant")
                    and num(t, "thresh") >= num(s, "thresh")
                    and card(t, "cq") <= card(s, "cq") and card(t, "dcq") <= card(s, "dcq")):
                raise UnifyTrap
        elif s.is_non_deriv():
            if not t.is_non_deriv():
                raise UnifyTrap
        elif s.is_num_quant():
            ok = False
            if t.is_num_quant():
                ti = num(t, "emin") if t.nodeset("emin") else 0
                tj = num(t, "emax") if t.nodeset("emax") else 0
                tn = card(t, "etot")
                si = num(s, "emin") if s.nodeset("emin") else 0
                sj = num(s, "emax") if s.nodeset("emax") else 0
                sn = card(s, "etot")
                ok = (ti == max(si - max(sn - tn, 0), 0) and tj == sj
                      and card(t, "&ant") == card(s, "&ant") and card(t, "cq") <= card(s, "cq"))
            if not ok:
                raise UnifyTrap
        elif self._rulep(t):
            raise UnifyTrap

    def _unifynss(self, tnss: list, snss: list, tb: list, sb: list, initt: Any,
                  inits: Any) -> list:
        if not tnss:
            return [[sb, tb]]
        if not tnss[0]:
            return self._unifynss(tnss[1:], snss[1:], tb, sb, initt, inits)
        return self._unifynss1(tnss[0][0], tnss, snss, tb, sb, initt, inits)

    def _unifynss1(self, tn: Node, tnss: list, snss: list, tb: list, sb: list,
                   initt: Any, inits: Any) -> list:
        bindgsfortn: list = []
        for sn in snss[0]:
            bindings: list = []
            try:
                here = self._here(tn, sn, copy_alist(tb), copy_alist(sb), initt, inits, False)
            except UnifyTrap:
                here = []
            for bndg in here:
                try:
                    res = self._unifynss([tnss[0][1:]] + tnss[1:],
                                         [tuple(x for x in snss[0] if x is not sn)] + snss[1:],
                                         bndg[1], bndg[0], initt, inits)
                except UnifyTrap:
                    res = []
                bindings = res + bindings
            bindgsfortn = bindings + bindgsfortn
        if bindgsfortn:
            return bindgsfortn
        raise UnifyTrap

    def _var_here(self, u: Node, term: Node, r1: list, r2: list, ir1: Any, ir2: Any,
                  t2istarget: bool) -> list:
        def pair(a: list, b: list) -> list:
            return [a, b] if t2istarget else [b, a]

        def through(y: Any, r1: list, r2: list) -> list:
            out = []
            for bndg in self._here(y, term, r1, r2, ir1, ir2, t2istarget):
                if t2istarget:
                    out.append([aset(bndg[0], u, y), bndg[1]])
                else:
                    out.append([bndg[0], aset(bndg[1], u, y)])
            return out
        y = aget(r1, u)
        if y is not None:
            if term is y:
                return [pair(r1, r2)]
            if term.is_var:
                if _uvbr(y) and y[1] is term:
                    return [pair(r1, r2)]
                raise UnifyTrap
            if term.is_base:
                raise UnifyTrap
            r1 = aset(r1, u, LOOP)
            return through(y, r1, r2)
        iu = binding_of(u, ir1) if ir1 else None
        if iu is not None and iu is not u:
            if term is iu:
                r1 = aset(r1, u, term)
                return [pair(r1, r2)]
            if term.is_var:
                z2 = aget(r2, term)
                zi = binding_of(term, ir2) if ir2 else None
                if z2 is None and zi is None:
                    r1 = aset(r1, u, iu)
                    r2 = aset(r2, term, iu)
                    return [pair(r1, r2)]
                z = z2 if z2 is not None else zi
                if iu is z:
                    r1 = aset(r1, u, iu)
                    r2 = aset(r2, term, z)
                    return [pair(r1, r2)]
                r1 = aset(r1, u, LOOP)
                r2 = aset(r2, term, z)
                return through(iu, r1, r2)
            r1 = aset(r1, u, LOOP)
            return through(iu, r1, r2)
        if ns_ismemb(u, term.get_freevars()):
            raise UnifyTrap
        if arassoc(r1, term) or ahas(r2, term):
            raise UnifyTrap
        r1 = aset(r1, u, term)
        if term.is_var:
            if t2istarget:
                r1 = aset(r1, u, ("uvbr", term))
                r2 = aset(r2, term, u)
            else:
                r2 = aset(r2, term, ("uvbr", u))
        return [pair(r1, r2)]

    def _vere(self, v: Node, r1: list, r2: list, s1: dict, s2: dict) -> Any:
        rv = aget(r1, v)
        if rv is not None:
            if _uvbr(rv):
                z = rv[1]
                s1[v] = v
                s2[z] = v
                r1 = aset(r1, v, DONE)
                r2 = aset(r2, z, DONE)
                return v
            if isinstance(rv, Node) and (rv.is_base or rv.is_mol):
                s1[v] = rv
                aset(r1, v, DONE)
                return rv
            if isinstance(rv, Node) and rv.is_pat:
                r1 = aset(r1, v, DONE)
                s1[v] = LOOP
                z = self._term_vere(rv, r2, r1, s2, s1)
                s1[v] = z
                return z
            sv = s1.get(v)
            if sv is not None:
                if sv == LOOP:
                    raise UnifyTrap
                return sv
            return rv
        aset(r1, v, DONE)
        s1[v] = v
        return v

    def _term_vere(self, term: Node, r1: list, r2: list, s1: dict, s2: dict) -> Node:
        ans: list = []
        for ri, nsi in self.down_fcs(term):
            for ti in nsi:
                if ti.is_var:
                    rv = aget(r1, ti)
                    if rv == DONE and not isinstance(rv, Node):
                        if s1.get(ti) == LOOP:
                            raise UnifyTrap
                        ans = cs_insert(ans, ri, (s1.get(ti),))
                    elif rv is not None:
                        ans = cs_insert(ans, ri, (self._vere(ti, r1, r2, s1, s2),))
                    else:
                        ans = cs_insert(ans, ri, (ti,))
                elif ti.is_pat:
                    ans = cs_insert(ans, ri, (self._term_vere(ti, r1, r2, s1, s2),))
                else:
                    ans = cs_insert(ans, ri, (ti,))
        return self.find_or_build(ans)[0]

    # ------------------------------------------------------------------
    def unify(self, source: Node, target: Node, initsbind: Any = None,
              inittbind: Any = None) -> tuple[list, list]:
        """Most general unifier pairs ``(source-sub, target-sub)`` of SOURCE and
        TARGET, and the list of ``(new-node, target-sub)`` instances."""
        new_nodes: list = []
        sublist: list = []
        with self.let(match_supporting_nodes=[], match_top_node=source):
            try:
                rpairs = self._here(target, source, [], [], inittbind, initsbind, False)
                for rpair in rpairs:
                    ssource: dict = {}
                    starget: dict = {}
                    for p in list(rpair[1]):
                        if not (p[1] == DONE and not isinstance(p[1], Node)):
                            self._vere(p[0], rpair[1], rpair[0], starget, ssource)
                    for p in list(rpair[0]):
                        if not (p[1] == DONE and not isinstance(p[1], Node)):
                            self._vere(p[0], rpair[0], rpair[1], ssource, starget)
                    s = tuple((v, trm) for v, trm in ssource.items()
                              if not (isinstance(trm, Node) and trm.is_var))
                    tr = tuple(starget.items())
                    sublist.insert(0, [s, tr])
                    new_nodes.insert(0, [self._create_new_node(target, tr, source), tr])
            except UnifyTrap:
                return [], new_nodes
        return sublist, new_nodes

    def _create_new_node(self, target: Node, tr: tuple, top_node: Node) -> Node:
        sup = self.compute_support(tr, self.match_supporting_nodes)
        new = self.applysubst(target, tr) if sup else top_node
        if sup:
            self.addsupport(sup, new)
        return new

    def match(self, tnode: Node, initbind: Any = None) -> list:
        """Matchings ``[node, sub, sub]`` of the nodes that unify with TNODE."""
        initbind = tuple(initbind or ())
        if any(self.dominates(tnode, p[1]) for p in initbind):
            return []
        sub_tnode = self.applysubst(tnode, initbind)
        out = []
        for psn in self.potential_source_nodes(tnode):
            sublist, new_nodes = self.unify(psn, sub_tnode)
            for bndg in sublist:
                if not uvbr_conflict(initbind, bndg[1]):
                    tb = tuple(bndg[1]) + self.substitute_in_terms(initbind, bndg[1])
                    if not violates_uvbr(tb):
                        node = psn if not new_nodes else _get_new_node(new_nodes, bndg[1])
                        out.append([node, bndg[0], tb])
        return out

    def forward_match(self, snode: Node, initbind: Any = None) -> list:
        initbind = tuple(initbind or ())
        sub_node = self.applysubst(snode, initbind)
        out = []
        for ptn in self.potential_target_nodes(snode):
            sublist, _new = self.unify(sub_node, ptn)
            for bndg in sublist:
                out.append([ptn, tuple(bndg[0]) + self.substitute_in_terms(initbind, bndg[0]),
                            bndg[1]])
        return out

    def match_in_context(self, tnode: Node, ct: Any, initbind: Any = None) -> list:
        with self.let(crntct=ct):
            out: list = []
            for m in self.match(tnode, initbind):
                if self.in_context_ns([m[0]], True):
                    out.insert(0, [m[0], m[1], self.filter_sup(m[0].asupport, ct), m[2]])
            return out

    def forward_match_in_context(self, snode: Node, ct: Any, initbind: Any = None) -> list:
        with self.let(crntct=ct):
            out: list = []
            for m in self.forward_match(snode, initbind):
                if self.in_context_ns([m[0]], True):
                    out.insert(0, [m[0], m[1], self.filter_sup(m[0].asupport, ct), m[2]])
            return out

    def filter_sup(self, sup: tuple, ct: Any) -> tuple:
        from ..core.nodeset import ctcs_filter
        c = self.get_context(ct) if not hasattr(ct, "hyps") else ct
        return ctcs_filter(sup, c) if c is not None else ()

    def potential_source_nodes(self, tnode: Node) -> tuple:
        if tnode.is_base:
            return ns_insert(tnode, self.value_sv("varnodes") or ())
        nodes = self.all_nodes()
        if tnode.is_var:
            return nodes
        rels = [r for r, _ns in self.down_fcs(tnode) if r not in self.up_relations]
        alts = [self.altrels.get(r) or [r] for r in rels]

        def potential(n: Node) -> bool:
            if n.is_var:
                return True
            if n is tnode or n.is_base:
                return False
            fcs = n.fcableset
            return any(any(fcs.get(a) for a in alt) for alt in alts)
        return tuple(n for n in nodes if potential(n))

    def potential_target_nodes(self, snode: Node) -> tuple:
        if snode.is_base:
            return ns_insert(snode, self.value_sv("varnodes") or ())
        return tuple(n for n in self.all_nodes() if not n.is_base)

    def applysubst(self, pnode: Node, sbst: Any) -> Node:
        """PNODE with each variable bound in SBST replaced by its term."""
        if pnode.is_base or pnode.is_mol:
            return pnode
        if pnode.is_var:
            return binding_of(pnode, sbst) or pnode
        b = binding_of(pnode, sbst)
        if b is not None:
            return b
        return self._term_vere(pnode, copy_alist(sbst), [], {}, {})

    def substitute_in_terms(self, b1: Iterable, b2: Iterable) -> tuple:
        b2 = tuple(b2)
        return tuple((p[0], self.applysubst(p[1], b2)) for p in b1)

    # ------------------------------------------------------------------
    # support of path-based matches (compute-support)
    def compute_support(self, tr: Iterable, supporting_nodes: Any) -> tuple:
        if supporting_nodes is UNBOUND or not supporting_nodes:
            supporting_nodes = []
        sup_nodes: list = []
        for one in tr:
            sup_nodes = _get_supporting_nodes(one[1], supporting_nodes) + sup_nodes
        combined = _combine_nodes(sup_nodes)
        l: list = []
        for el in [[n.asupport for n in ns] for ns in reversed(combined)] if combined else []:
            l.extend(_combine_supps(el))
        support: tuple = ()
        from ..core.nodeset import ctcs_insert
        for ots, cts in l:
            support = ctcs_insert(combine_ots(ots), self.fullbuildcontext((), cts), support)
        return support


def combine_ots(otlst: Iterable[str]) -> str:
    return "ext" if "ext" in otlst else "der"


def _get_new_node(new_nodes: list, tr: Any) -> Node:
    for n in new_nodes:
        if n[1] is tr or _sub_equal(n[1], tr):
            return n[0]
    return new_nodes[0][0]


def _sub_equal(a: Iterable, b: Iterable) -> bool:
    a, b = tuple(a), tuple(b)
    return len(a) == len(b) and all(x[0] is y[0] and x[1] is y[1] for x, y in zip(a, b))


def _get_supporting_nodes(node: Node, l: list) -> list:
    for el in l:
        aux = [p[1] for p in el if p[0] is node]
        if aux:
            return [aux]
    return []


def _combine_nodes(l: list) -> list:
    if not l:
        return []
    result = l[0]
    for lst in l[1:]:
        result1: list = []
        for res in result:
            for res1 in lst:
                result1.insert(0, ns_union(res1, res))
        result = result1
    return result


def _flatten_supports(sup: tuple) -> list:
    result: list = []
    for ot, cts in sup:
        result = [[[ot], [x]] for x in cts] + result
    return result


def _combine_supps(l: list) -> list:
    flat = [_flatten_supports(s) for s in l]
    if not flat:
        return []
    result = flat[0]
    for lst in flat[1:]:
        result1: list = []
        for res in result:
            for res1 in lst:
                result1.insert(0, [res1[0] + res[0], res1[1] + res[1]])
        result = result1
    return result
