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
"""Node sets and context sets (``sneps/ds/nodeset``, ``contextset``).

A node set is a tuple of nodes ordered newest first (by decreasing creation
order); a context set is a tuple of contexts ordered the same way.  All
operations are non-destructive and keep that order, as in SNePS 2.8.
"""

from __future__ import annotations

from typing import Callable, Iterable

EMPTY: tuple = ()


# -- node sets ---------------------------------------------------------------

def ns_insert(n, ns: tuple) -> tuple:
    """INSERT.NS: NS with N inserted before the first older node."""
    if not ns:
        return (n,)
    order = n.order
    for i, x in enumerate(ns):
        if x is n:
            return ns
        if x.order < order:
            return ns[:i] + (n,) + ns[i:]
    return ns + (n,)


def ns_make(nodes: Iterable) -> tuple:
    """A node set containing NODES (SEQ-TO-NS)."""
    ns: tuple = ()
    for n in nodes:
        ns = ns_insert(n, ns)
    return ns


def ns_union(ns1: tuple, ns2: tuple) -> tuple:
    if not ns2:
        return ns1
    if not ns1:
        return ns2
    if len(ns2) == 1:
        return ns_insert(ns2[0], ns1)
    if len(ns1) == 1:
        return ns_insert(ns1[0], ns2)
    seen = {id(n) for n in ns1}
    out = ns1
    for n in ns2:
        if id(n) not in seen:
            out = ns_insert(n, out)
    return out


def ns_intersect(ns1: tuple, ns2: tuple) -> tuple:
    if not ns1:
        return ns1
    if not ns2:
        return ns2
    seen = {id(n) for n in ns1}
    return tuple(n for n in ns2 if id(n) in seen)


def ns_compl(ns1: tuple, ns2: tuple) -> tuple:
    """The nodes of NS1 that are not in NS2."""
    if not ns1 or not ns2:
        return ns1
    seen = {id(n) for n in ns2}
    return tuple(n for n in ns1 if id(n) not in seen)


def ns_issubset(ns1: tuple, ns2: tuple) -> bool:
    if not ns1:
        return True
    if not ns2:
        return False
    seen = {id(n) for n in ns2}
    return all(id(n) in seen for n in ns1)


def ns_member(n, ns: Iterable) -> bool:
    """Full membership test."""
    return any(x is n for x in ns)


def ns_ismemb(n, ns: Iterable) -> bool:
    """ISMEMB.NS: scans NS only until the first node not newer than N.

    As in SNePS 2.8 this assumes NS is ordered newest first, so on an
    unordered node set it can miss N; SNIP's behaviour depends on that.
    """
    order = n.order
    for x in ns:
        if x is n:
            return True
        if x.order < order:
            return False
    return False


def ns_remove(n, ns: tuple) -> tuple:
    for i, x in enumerate(ns):
        if x is n:
            return ns[:i] + ns[i + 1:]
    return ns


def ns_filter(pred: Callable, ns: tuple) -> tuple:
    return tuple(n for n in ns if pred(n))


def ns_choose(ns):
    return ns[0] if ns else None


# -- context sets ------------------------------------------------------------

def cts_insert(c, cts: tuple) -> tuple:
    if not cts:
        return (c,)
    order = c.order
    for i, x in enumerate(cts):
        if x is c:
            return cts
        if order > x.order:
            return cts[:i] + (c,) + cts[i:]
    return cts + (c,)


def cts_make(contexts: Iterable) -> tuple:
    cts: tuple = ()
    for c in contexts:
        cts = cts_insert(c, cts)
    return cts


def cts_union(cts1: tuple, cts2: tuple) -> tuple:
    out = list(cts1)
    for c in cts2:
        if not any(x is c for x in out):
            out.append(c)
    out.sort(key=lambda c: -c.order)
    return tuple(out)


def cts_intersect(cts1: tuple, cts2: tuple) -> tuple:
    ids = {id(c) for c in cts2}
    return tuple(c for c in cts1 if id(c) in ids)


def cts_compl(cts1: tuple, cts2: tuple) -> tuple:
    ids = {id(c) for c in cts2}
    return tuple(c for c in cts1 if id(c) not in ids)


def cts_member(c, cts: Iterable) -> bool:
    return any(x is c for x in cts)


def cts_remove(c, cts: tuple) -> tuple:
    return tuple(x for x in cts if x is not c)


def cts_issubset(cts1: tuple, cts2: tuple) -> bool:
    ids = {id(c) for c in cts2}
    return all(id(c) in ids for c in cts1)


# -- context cable sets (support) ---------------------------------------------
# A support is a tuple of (origin-tag, context-set) pairs; origin tags are
# 'hyp', 'der' and 'ext'.

def ctcs_get(ot: str, ctcs: tuple) -> tuple:
    for o, cts in ctcs:
        if o == ot:
            return cts
    return ()


def ctcs_insert(ot: str, ct, ctcs: tuple) -> tuple:
    """INSERT.CTCS: unchanged if some context of CTCS is a subset of CT."""
    if not ctcs:
        return ((ot, (ct,)),)
    hyps = ct.hyps
    for _o, cts in ctcs:
        for old in cts:
            if ns_issubset(old.hyps, hyps):
                return ctcs
    for i, (o, cts) in enumerate(ctcs):
        if o == ot and cts:
            return ctcs[:i] + ((o, cts_insert(ct, cts)),) + ctcs[i + 1:]
    return ((ot, (ct,)),) + ctcs


def ctcs_filter(sup: tuple, ct) -> tuple:
    """FILTER.CTCS: the part of support SUP whose contexts are within CT."""
    out: tuple = ()
    for ot, cts in sup:
        for c in cts:
            if ns_issubset(c.hyps, ct.hyps):
                out = ctcs_insert(ot, c, out)
    return out


def ctcs_to_cts(ctcs: tuple) -> tuple:
    out: tuple = ()
    for _ot, cts in ctcs:
        out = out + tuple(cts)
    return out


def ctcs_to_ots(ctcs: tuple) -> list:
    out: list = []
    for ot, cts in ctcs:
        out.extend([ot] * len(cts))
    return out
