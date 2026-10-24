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
"""SNIP data structures (``snip/ds/*``, ``snip/fns/support``).

* substitutions, filters and switches: tuples of ``(variable, term)`` pairs;
* supports: tuples of ``(origin-tag, context-set)`` pairs (see
  :mod:`sneps.core.nodeset`);
* channels and feeders are mutable (their valve can be opened or closed);
* reports, instances, flagged nodes and rule-use infos are immutable tuples.

Sets of these are Python lists ordered as in SNePS 2.8 (new elements are
pushed on the front unless stated otherwise).
"""

from __future__ import annotations

from typing import Any, Iterable, NamedTuple, Optional

from ..core.node import Node
from ..core.nodeset import ctcs_get, ctcs_insert, cts_compl, cts_insert, ns_ismemb
from ..util.lists import union as ordered_union

POS = "POS"
NEG = "NEG"
OPEN = "OPEN"
CLOSED = "CLOSED"
USER = "USER"
SENSOR = "SENSOR"
TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"
REQUESTED = "REQUESTED"


def ct_eq(a: Any, b: Any) -> bool:
    """ISEQ.CT on context designators (context objects or names)."""
    return a is b or (isinstance(a, str) and a == b)


def node_eq(a: Any, b: Any) -> bool:
    """ISEQ.N / ISEQ.DEST (nodes, or the symbols USER and SENSOR)."""
    return a is b or (isinstance(a, str) and a == b)


# ---------------------------------------------------------------------------
# substitutions

def mb_equal(a: tuple, b: tuple) -> bool:
    return a[0] is b[0] and a[1] is b[1]


def sbst_binding(v: Any, s: Iterable) -> Any:
    for p in s or ():
        if p[0] is v:
            return p[1]
    return None


def sbst_is_bound(v: Any, s: Iterable) -> bool:
    return any(p[0] is v for p in s or ())


def sbst_member(mb: tuple, s: Iterable) -> bool:
    return any(mb_equal(mb, p) for p in s or ())


def sbst_issubset(s1: Iterable, s2: Iterable) -> bool:
    s2 = tuple(s2 or ())
    return all(sbst_member(mb, s2) for mb in s1 or ())


def sbst_eq(s1: Iterable, s2: Iterable) -> bool:
    s1, s2 = tuple(s1 or ()), tuple(s2 or ())
    return sbst_issubset(s1, s2) and sbst_issubset(s2, s1)


def sbst_putin(mb: tuple, s: Iterable) -> tuple:
    s = tuple(s or ())
    if sbst_member(mb, s):
        return s
    return (mb,) + s


def sbst_union(s1: Iterable, s2: Iterable) -> tuple:
    """UNION.SBST: the pairs of S2 whose variable is unbound in S1, then S1."""
    s1 = tuple(s1 or ())
    out = s1
    for mb in reversed(tuple(s2 or ())):
        if not sbst_is_bound(mb[0], s1):
            out = sbst_putin(mb, out)
    return out


def sbst_restrict(s: Iterable, ns: Iterable) -> tuple:
    ns = tuple(ns or ())
    return tuple(mb for mb in s or () if ns_ismemb(mb[0], ns))


def sbst_is_compatible(s1: Iterable, s2: Iterable) -> bool:
    s2 = tuple(s2 or ())
    for v, t in s1 or ():
        t2 = None
        found = False
        for p in s2:
            if p[0] is v:
                t2, found = p[1], True
                break
        if found:
            if t2 is not t:
                return False
        elif any(p[1] is t for p in s2):
            return False
    return True


def sbst_set_difference(s1: Iterable, s2: Iterable) -> tuple:
    s2 = tuple(s2 or ())
    return tuple(mb for mb in s1 or () if not sbst_member(mb, s2))


def sbst_set_member(s: Iterable, sets: Iterable) -> bool:
    """(MEMBER S SETS :TEST #'EQUAL) for substitutions."""
    s = tuple(s or ())
    for x in sets or ():
        x = tuple(x or ())
        if len(x) == len(s) and all(mb_equal(a, b) for a, b in zip(s, x)):
            return True
    return False


def restr_equivalent(s1: Iterable, s2: Iterable) -> bool:
    """EQUIVALENT.RESTR on the substitutions of two restrictions."""
    s1, s2 = tuple(s1 or ()), tuple(s2 or ())
    if len(s1) != len(s2):
        return False
    for v, t in s1:
        term = sbst_binding(v, s2)
        if term is None or term is not t:
            return False
    return True


def filter_ok(subst: Iterable, filt: Iterable) -> bool:
    """FILTER: SUBST agrees with every binding of FILT."""
    for var, tf in filt or ():
        ts = sbst_binding(var, subst)
        if ts is None or ts is not tf:
            return False
    return True


def compatible(subst: Iterable, filt: Iterable) -> bool:
    filt = tuple(filt or ())
    for var, ts in subst or ():
        tf = sbst_binding(var, filt)
        varf = next((p[0] for p in filt if p[1] is ts), None)
        if (tf is not None and ts is not tf) or (varf is not None and var is not varf):
            return False
    return True


def get_var_bindings(sbst: Iterable) -> tuple:
    return tuple(b for b in sbst or () if isinstance(b[0], Node) and b[0].is_var)


# ---------------------------------------------------------------------------
# supports

def sup_merge(sup1: tuple, sup2: tuple) -> tuple:
    for ot, cts in sup1 or ():
        for ct in cts:
            sup2 = ctcs_insert(ot, ct, sup2)
    return sup2


def sup_len(sup: tuple) -> int:
    return 2 * len(sup or ())


def sup_eq(sup1: tuple, sup2: tuple) -> bool:
    if sup_len(sup1) != sup_len(sup2):
        return False
    return sup_included(sup1, sup2)


def sup_included(sup1: tuple, sup2: tuple) -> bool:
    for ot, cts1 in sup1 or ():
        if cts_compl(cts1, ctcs_get(ot, sup2)):
            return False
    return True


def combine_ots(ot1: str, ot2: str) -> str:
    return "ext" if (ot1 == "ext" or ot2 == "ext") else "der"


def combine_ots_star(otlst: Iterable[str]) -> str:
    return "ext" if "ext" in list(otlst) else "der"


def not_all_ct_equal(ctlist: list) -> bool:
    if not ctlist:
        return False
    first = ctlist[0]
    return any(c is not first for c in ctlist[1:])


def combine_and_intr_ots_star(otlst: Iterable[str], ctlist: list) -> str:
    return "ext" if ("ext" in list(otlst) or not_all_ct_equal(ctlist)) else "der"


def sup_to_lists(sup: tuple) -> list:
    out: list = []
    for ot, cts in sup or ():
        out = [[ot], list(cts)] + out
    return out


def sup_to_combinations(sup: tuple) -> list:
    out: list = []
    for ot, cts in sup or ():
        for ct in cts:
            out = [[ot], [ct]] + out
    return out


def combinations_of(sup: tuple, lst_of_sups: list) -> list:
    if not lst_of_sups:
        return sup_to_lists(sup)
    return _combinations_of_1(sup, lst_of_sups)


def _combinations_of_1(sup: tuple, lst_of_sups: list) -> list:
    out: list = []
    rest = combinations_of(lst_of_sups[0], lst_of_sups[1:])
    for ot, cts in sup or ():
        out = out + _comb_ot_ct(ot, cts, rest)
    return out


def _comb_ot_ct(ot: str, cts: tuple, suplist: list) -> list:
    result: list = []
    for ct in cts:
        for i in range(0, len(suplist), 2):
            ots1, cts1 = suplist[i], suplist[i + 1]
            result = [[ot] + list(ots1), list(cts_insert(ct, tuple(cts1)))] + result
    return result


def change_tag_support(sup: tuple) -> tuple:
    new: tuple = ()
    for ot, cts in sup or ():
        for ct in cts:
            new = ctcs_insert("der" if ot == "hyp" else ot, ct, new)
    return new


def non_hyp(sup: tuple) -> tuple:
    return tuple(("der" if ot == "hyp" else ot, cts) for ot, cts in sup or ())


# ---------------------------------------------------------------------------
# channels and feeders

class Channel:
    __slots__ = ("filter", "switch", "context", "destination", "valve")

    def __init__(self, filt: Any, switch: Any, context: Any, destination: Any, valve: str):
        self.filter = tuple(filt or ())
        self.switch = tuple(switch or ())
        self.context = context
        self.destination = destination
        self.valve = valve

    def is_open(self) -> bool:
        return self.valve == OPEN

    def __repr__(self) -> str:
        return (f"#<channel {list(self.filter)} {list(self.switch)} {self.context} "
                f"{self.destination} {self.valve}>")


def ch_equivalent(c1: Channel, c2: Channel) -> bool:
    return (node_eq(c1.destination, c2.destination)
            and restr_equivalent(c1.filter, c2.filter)
            and restr_equivalent(c1.switch, c2.switch)
            and ct_eq(c1.context, c2.context))


def chset_insert(ch: Channel, chset: list) -> list:
    for c in chset:
        if ch_equivalent(c, ch):
            c.valve = ch.valve
            return chset
    return [ch] + chset


class Feeder:
    __slots__ = ("restriction", "context", "source", "valve")

    def __init__(self, restriction: Any, context: Any, source: Any, valve: str):
        self.restriction = tuple(restriction or ())
        self.context = context
        self.source = source
        self.valve = valve


def feeder_equivalent(f1: Feeder, f2: Feeder) -> bool:
    return (ct_eq(f1.context, f2.context) and node_eq(f1.source, f2.source)
            and restr_equivalent(f1.restriction, f2.restriction))


def feedset_insert(feeder: Feeder, fs: list) -> list:
    for f in fs:
        if feeder_equivalent(f, feeder):
            f.valve = feeder.valve
            return fs
    return [feeder] + fs


# ---------------------------------------------------------------------------
# reports

class Report(NamedTuple):
    subst: tuple
    support: tuple
    sign: str
    signature: Any
    node: Any
    context: Any


def rep_eq(r1: Report, r2: Report) -> bool:
    return (sbst_eq(r1.subst, r2.subst) and sup_eq(r1.support, r2.support)
            and r1.sign == r2.sign and node_eq(r1.signature, r2.signature)
            and ct_eq(r1.context, r2.context)
            and ((r1.node is None and r2.node is None)
                 or (r1.node is not None and r2.node is not None and r1.node is r2.node)))


def repset_insert(r: Report, repset: list) -> list:
    if any(rep_eq(r, x) for x in repset):
        return repset
    return [r] + repset


def repset_union(s1: list, s2: list) -> list:
    return ordered_union(s1, s2, rep_eq)


# ---------------------------------------------------------------------------
# instances

class Instance(NamedTuple):
    subst: tuple
    support: tuple
    sign: str


def inst_merge(i1: Instance, i2: Instance) -> Instance:
    return Instance(i1.subst, sup_merge(i1.support, i2.support), i1.sign)


def iset_member(inst: Instance, iset: list) -> bool:
    return any(sbst_eq(inst.subst, i.subst) and sup_included(inst.support, i.support)
               and inst.sign == i.sign for i in iset)


def iset_insert(inst: Instance, iset: list) -> list:
    if iset_member(inst, iset):
        return iset
    fin: list = []
    found = False
    for i in iset:
        if sbst_eq(i.subst, inst.subst) and i.sign == inst.sign:
            fin = [inst_merge(i, inst)] + fin
            found = True
        else:
            fin = [i] + fin
    if found:
        return fin
    return [inst] + iset


# ---------------------------------------------------------------------------
# flagged nodes and rule-use infos

class FNode(NamedTuple):
    node: Node
    support: tuple
    flag: str


def fns_flag(n: Node, fns: Iterable[FNode]) -> Optional[str]:
    for fn in fns:
        if fn.node is n:
            return fn.flag
    return None


def fns_support(n: Node, fns: Iterable[FNode]) -> tuple:
    for fn in fns:
        if fn.node is n:
            return fn.support
    return ()


def fns_update(fns: tuple, n: Node, sup: tuple, flag: str) -> tuple:
    fns = tuple(fns)
    for i, fn in enumerate(fns):
        if fn.node is n:
            return fns[:i] + (FNode(n, sup_merge(sup, fn.support), flag),) + fns[i + 1:]
    return fns


def nodeset_to_fnodeset(ns: Iterable[Node]) -> tuple:
    out: tuple = ()
    for n in ns:
        out = (FNode(n, (), UNKNOWN),) + out
    return out


def fns_to_suplist(fns: Iterable[FNode]) -> list:
    out: list = []
    for fn in fns:
        if fn.support:
            out = [fn.support] + out
    return out


class RUI(NamedTuple):
    subst: tuple
    poscount: int
    negcount: int
    fns: tuple
    remarkedp: bool


def rui_update(rui: RUI, node: Node, sup: tuple, sign: str) -> RUI:
    if sign == POS:
        return RUI(rui.subst, rui.poscount + 1, rui.negcount,
                   fns_update(rui.fns, node, sup, TRUE), rui.remarkedp)
    return RUI(rui.subst, rui.poscount, rui.negcount + 1,
               fns_update(rui.fns, node, sup, FALSE), rui.remarkedp)


def rui_merge(rui1: RUI, rui2: RUI) -> RUI:
    fns2 = rui2.fns
    newfns: tuple = ()
    pos, neg = rui1.poscount, rui1.negcount
    for fn1 in rui1.fns:
        n1, f1, s1 = fn1.node, fn1.flag, fn1.support
        f2 = fns_flag(n1, fns2)
        s2 = fns_support(n1, fns2)
        if f1 in (TRUE, FALSE):
            newfns = (FNode(n1, sup_merge(s1, s2), f1),) + newfns
        elif f2 == TRUE:
            newfns = (FNode(n1, s2, f2),) + newfns
            pos += 1
        elif f2 == FALSE:
            newfns = (FNode(n1, s2, f2),) + newfns
            neg += 1
        elif f2 == REQUESTED:
            newfns = (FNode(n1, s2, f2),) + newfns
        else:
            newfns = (fn1,) + newfns
    return RUI(rui1.subst, pos, neg, newfns, True)


def rui_compatible(rui1: RUI, rui2: RUI) -> bool:
    fns2 = rui2.fns
    for fn1 in rui1.fns:
        f1 = fn1.flag
        f2 = fns_flag(fn1.node, fns2)
        if (f1 == TRUE and f2 == FALSE) or (f1 == FALSE and f2 == TRUE):
            return False
    return True


def rui_select(rui: RUI, flags: tuple) -> tuple:
    out: tuple = ()
    for fn in rui.fns:
        if fn.flag in flags:
            out = (fn,) + out
    return out


def ruis_update(updated: RUI, ruiset: list) -> list:
    out_prefix: list = []
    for i, r in enumerate(ruiset):
        if sbst_eq(updated.subst, r.subst) and rui_compatible(updated, r):
            return out_prefix + [rui_merge(updated, r)] + list(ruiset[i + 1:])
        out_prefix.append(r)
    return out_prefix + [updated]


def request_all(ruis: list) -> list:
    return [RUI(r.subst, r.poscount, r.negcount,
                tuple(FNode(fn.node, fn.support, REQUESTED if fn.flag == UNKNOWN else fn.flag)
                      for fn in r.fns), r.remarkedp) for r in ruis]


# ---------------------------------------------------------------------------
# rule-use channels and introduction channels

class Cqch(NamedTuple):
    channel: Channel
    ants: tuple
    ruiset: Any       # list of RUIs, an S-index alist, or a P-tree triple


def cqchset_insert(cqch: Cqch, cqchs: list) -> list:
    for c in cqchs:
        if ch_equivalent(cqch.channel, c.channel):
            return cqchs
    return list(cqchs) + [cqch]


def cqchset_update(cqch: Cqch, cqchs: list) -> list:
    for i, c in enumerate(cqchs):
        if ch_equivalent(cqch.channel, c.channel):
            return list(cqchs[:i]) + [cqch] + list(cqchs[i + 1:])
    return list(cqchs) + [cqch]


def get_updated_cqch(cqch: Cqch, cqchs: list) -> Optional[Cqch]:
    result = None
    for c in cqchs:
        if ch_equivalent(cqch.channel, c.channel):
            result = c
    return result


class Ich(NamedTuple):
    channel: Channel
    context: tuple        # the assumed antecedents
    consequents: tuple
    ruiset: list


def ichset_insert(ich: Ich, ichs: list) -> list:
    for c in ichs:
        if ch_equivalent(ich.channel, c.channel):
            return ichs
    return list(ichs) + [ich]


def ichset_update(ich: Ich, ichs: list) -> list:
    for i, c in enumerate(ichs):
        if (ch_equivalent(ich.channel, c.channel) and _ns_equal(ich.context, c.context)
                and _ns_equal(ich.consequents, c.consequents)):
            return list(ichs[:i]) + [ich] + list(ichs[i + 1:])
    return list(ichs) + [ich]


def _ns_equal(a: Any, b: Any) -> bool:
    a, b = tuple(a or ()), tuple(b or ())
    return len(a) == len(b) and all(x is y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# P-trees (snip/ds/ptree)

class Cell(list):
    """A mutable alist cell ``[key, value]`` (shared between holders)."""


def alist_assoc(key: Any, al: list) -> Optional[Cell]:
    for cell in al:
        if cell[0] == key:
            return cell
    return None


def alist_rassoc_list(value: Any, al: list) -> Optional[Any]:
    """(RASSOC (LIST VALUE) AL :TEST 'EQUAL) on an adjacency list."""
    for pair in al:
        if list(pair[1:]) == [value]:
            return pair
    return None


def build_ptree(pats: Iterable[Node], all_vars: Any) -> Any:
    pats = list(pats)
    patvar = [[p] + list(all_vars(p)) for p in pats]
    varpat: list = []
    for pv in patvar:
        pat = pv[0]
        for var in pv[1:]:
            entry = next((e for e in varpat if e[0] is var), None)
            if entry is None:
                varpat.append([var, pat])
            else:
                entry[1:] = ordered_union(entry[1:], [pat])
    patseq = _varpat_to_patseq(pats, patvar, varpat)
    return _patseq_to_ptree(patseq, patvar)


def _assoc_rest(key: Any, al: list) -> list:
    for e in al:
        if e[0] == key:
            return list(e[1:])
    return []


def _varpat_to_patseq(pats: list, patvar: list, varpat: list) -> list:
    patseq: list = []
    var_union: list = []
    unprocessed = [e[0] for e in varpat]
    while not (len(pats) == len(patseq) or not unprocessed):
        current = unprocessed[0]
        for pat in _assoc_rest(current, varpat):
            if not any(pat is p for p in patseq):
                var_union = ordered_union(var_union, _assoc_rest(pat, patvar))
                patseq.append(pat)
        var_temp = [v for v in unprocessed[1:] if any(v is u for u in var_union)]
        if not var_temp:
            unprocessed = unprocessed[1:]
        else:
            unprocessed = [var_temp[0]] + [v for v in unprocessed[1:] if v is not var_temp[0]]
    if len(pats) == len(patseq):
        return patseq
    return patseq + [p for p in pats if not any(p is q for q in patseq)]


def _patseq_to_ptree(patseq: list, patvar: list) -> Any:
    ptree = list(patseq)
    plist: list = [list(x) for x in patvar]

    def vars_of(node: Any) -> list:
        return _assoc_rest(node, plist)
    while ptree and len(ptree) != 1:
        cur = ptree
        temp: list = []
        while cur:
            first = cur[0]
            sec = cur[1] if len(cur) > 1 else None
            if [v for v in vars_of(first) if any(v is w for w in vars_of(sec))]:
                parent = [first, sec]
                temp.append(parent)
                plist.insert(0, [parent] + ordered_union(vars_of(first), vars_of(sec)))
                cur = cur[2:]
            else:
                if not temp:
                    temp = [first]
                else:
                    prev = temp[-1]
                    parent = [prev, first]
                    temp = temp[:-1] + [parent]
                    plist.insert(0, [parent] + ordered_union(vars_of(first), vars_of(prev)))
                cur = cur[1:]
        ptree = temp
    return ptree[0] if ptree else None


def ptree_to_adj_list(ptree: Any) -> list:
    if not isinstance(ptree, list) or len(ptree) <= 1:
        return [[ptree, None]]
    return _get_adj_node_list(ptree)


def _get_adj_node_list(ptree: list) -> list:
    first, sec = ptree[0], ptree[1]
    fa, sa = not isinstance(first, list), not isinstance(sec, list)
    if fa and sa:
        return [[first, sec]]
    if fa:
        return _get_adj_node_list(sec) + [[first, sec]]
    if sa:
        return _get_adj_node_list(first) + [[first, sec]]
    return _get_adj_node_list(first) + _get_adj_node_list(sec) + [[first, sec]]
