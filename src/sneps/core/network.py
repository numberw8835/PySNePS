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
"""The :class:`NetworkBase` class: all state of one SNePS knowledge base.

This holds the state of one knowledge base: the node table and node-name
counters, the relations and their converses, SNePS variables (svars), the
context table and nogood sets.  Each :class:`~sneps.Network` is independent,
so several knowledge bases can be used in one Python process.
"""

from __future__ import annotations

import contextlib
import re
import sys
from typing import Any, Iterable, Iterator, Optional

from ..io.streams import NullOutputStream, OutputStream
from .context import Context
from .node import BASE, MOL, PAT, VAR, Node, number_name, symbol_type
from .nodeset import (ctcs_filter, ctcs_get, ctcs_insert, cts_insert, ns_compl,
                      ns_insert, ns_issubset, ns_remove, ns_union)

INITIAL_RELATIONS = (
    "attachedfunction", "&ant", "ant", "arg", "forall", "cq", "dcq", "default",
    "emax", "emin", "etot", "exists", "max", "min", "pevb", "thresh", "threshmax",
    "when", "whenever", "do", "if", "vars", "suchthat", "condition", "then", "else",
    "act", "plan", "goal", "action", "precondition", "effect", "object1", "object2")

QUANTIFIER_RELATIONS = ("forall", "exists", "pevb", "vars")

PRIORITY_RELATIONS = ("forall", "exists", "pevb", "min", "max", "thresh", "threshmax",
                      "emin", "emax", "etot", "ant", "&ant", "cq", "dcq", "arg",
                      "fname", "default")
_PRIORITY_INDEX = {r: i for i, r in enumerate(PRIORITY_RELATIONS)}

SYSTEM_SVARS = ("variables", "relations", "nodes", "command", "lastcommand",
                "errorcommand", "contexts", "lastvalue", "assertions", "patterns",
                "defaultct", "varnodes")

NODE_PREFIXES = ("b", "m", "v", "p", "tm", "tv", "tp")
_GENERATED_NAME = re.compile(r"(?:[bmvp]|t[mvp])[0-9]+$")
_TEMP_PREFIXES = ("tm", "tv", "tp")


class SNePSError(Exception):
    """An error signalled by SNePS (SNEPS-ERROR)."""

    def __init__(self, msg: str, module: Any = None, fn: Any = None):
        super().__init__(msg)
        self.msg = msg
        self.module = module
        self.fn = fn


class _NodeIndex:
    """A node set kept as an insertion-ordered dict, materialized on demand.

    Used for the large system node sets (``nodes``, ``assertions``, ...)
    so that adding a node does not copy the whole set.
    """

    __slots__ = ("_d", "_cache")

    def __init__(self, nodes: Iterable[Node] = ()):
        self._d: dict[int, Node] = {id(n): n for n in nodes}
        self._cache: Optional[tuple] = None

    def add(self, n: Node) -> None:
        if id(n) not in self._d:
            self._d[id(n)] = n
            self._cache = None

    def discard(self, n: Node) -> None:
        if self._d.pop(id(n), None) is not None:
            self._cache = None

    def __contains__(self, n: Node) -> bool:
        return id(n) in self._d

    def __len__(self) -> int:
        return len(self._d)

    def as_ns(self) -> tuple:
        if self._cache is None:
            self._cache = tuple(sorted(self._d.values(), key=lambda n: -n.order))
        return self._cache


_INDEXED_SVARS = ("nodes", "assertions", "patterns", "varnodes")


class NetworkBase:
    """Core SNePS state and the basic node, relation and context operations."""

    def __init__(self, output: Optional[Any] = None):
        if output is None:
            self.outunit = OutputStream(sys.stdout)
        elif isinstance(output, OutputStream):
            self.outunit = output
        elif output is False:
            self.outunit = NullOutputStream()
        else:
            self.outunit = OutputStream(output)
        self.inunit = None
        self.nodes_by_name: dict[str, Node] = {}
        self.node_counter = 0
        self.id_counters = {p: 0 for p in NODE_PREFIXES}
        self.context_counter = 0
        # relations
        self.converses: dict[str, str] = {}
        self.down_relations: set[str] = set()
        self.up_relations: set[str] = set()
        self.pathdefs: dict[str, Any] = {}
        self.altrels: dict[str, Any] = {}
        self.fwd_paths: dict[str, list] = {}
        # svars
        self.svars: dict[str, Any] = {}
        self.sysvars: set[str] = set()
        self._index: dict[str, _NodeIndex] = {}
        # contexts
        self.contexts: dict[tuple, Context] = {}
        self.nogoods: list[tuple] = []
        self.oknogoods: list[tuple] = []
        self.crntct: Any = "default-defaultct"
        self.infertrace = False
        self.assert_later = 0
        self.new_propositions: list = []
        for sv in SYSTEM_SVARS:
            self.newsys_sv(sv)
        self.svars["contexts"] = self.contexts

    # ------------------------------------------------------------------
    # dynamic (special) variables
    @contextlib.contextmanager
    def let(self, **bindings: Any) -> Iterator[None]:
        """Temporarily rebind attributes (restored on exit, even after an error)."""
        old = {k: getattr(self, k) for k in bindings}
        for k, v in bindings.items():
            setattr(self, k, v)
        try:
            yield
        finally:
            for k, v in old.items():
                setattr(self, k, v)

    def write(self, s: str) -> None:
        self.outunit.write(s)

    def fresh_line(self) -> None:
        self.outunit.fresh_line()

    # ------------------------------------------------------------------
    # SNePS variables (svar)
    def is_sv(self, name: Any) -> bool:
        return isinstance(name, str) and (name in self.svars or name in self._index)

    def newsys_sv(self, name: str) -> None:
        if self.is_sv(name):
            return
        self.sysvars.add(name)
        self._sv_store(name, None)
        if name != "variables":
            self._variables_adjoin(name)

    def issys_sv(self, name: Any) -> bool:
        return name in self.sysvars

    def _variables_adjoin(self, name: str) -> None:
        vs = self.svars.get("variables") or []
        if name not in vs:
            self.svars["variables"] = [name] + list(vs)

    def new_sv(self, name: str) -> Optional[str]:
        if self.is_sv(name):
            return None
        self._sv_store(name, None)
        self._variables_adjoin(name)
        return name

    def value_sv(self, name: Any) -> Any:
        if not isinstance(name, str):
            return None
        idx = self._index.get(name)
        if idx is not None:
            return idx.as_ns()
        return self.svars.get(name)

    def _sv_store(self, name: str, value: Any) -> None:
        if name in _INDEXED_SVARS:
            self._index[name] = _NodeIndex(value or ())
            self.svars.pop(name, None)
        else:
            self.svars[name] = value

    def set_sv(self, name: str, value: Any) -> Any:
        if self.is_sv(name):
            old = self.value_sv(name)
            if isinstance(old, Context):
                self.removename_ct(old, name)
        else:
            self.new_sv(name)
        self._sv_store(name, value)
        return value

    def remove_sv(self, name: str) -> None:
        """REMPROP :VAL -- the variable no longer exists."""
        self.svars.pop(name, None)
        self._index.pop(name, None)

    def sv_add(self, name: str, n: Node) -> None:
        """(set.sv name (insert.ns n (value.sv name))) for indexed svars."""
        idx = self._index.get(name)
        if idx is None:
            self.set_sv(name, ns_insert(n, self.value_sv(name) or ()))
        else:
            idx.add(n)

    def sv_remove(self, name: str, n: Node) -> None:
        idx = self._index.get(name)
        if idx is None:
            self.set_sv(name, ns_remove(n, self.value_sv(name) or ()))
        else:
            idx.discard(n)

    def sv_contains(self, name: str, n: Node) -> bool:
        idx = self._index.get(name)
        if idx is not None:
            return n in idx
        return any(x is n for x in (self.value_sv(name) or ()))

    # ------------------------------------------------------------------
    # relations (rel2)
    def is_r(self, r: Any) -> bool:
        return isinstance(r, str) and r in self.converses

    def new_r(self, r: str) -> str:
        conv = r + "-"
        self.converses[r] = conv
        self.converses[conv] = r
        self.down_relations.add(r)
        self.up_relations.add(conv)
        self.up_relations.discard(r)
        rels = self.svars.get("relations") or []
        if r not in rels:
            self.svars["relations"] = [r] + list(rels)
        return r

    def undefine_r(self, r: str) -> None:
        conv = self.converses.get(r)
        if conv is not None:
            self.converses.pop(conv, None)
            self.up_relations.discard(conv)
        self.converses.pop(r, None)
        self.down_relations.discard(r)
        rels = self.svars.get("relations") or []
        self.svars["relations"] = [x for x in rels if x != r] or None

    def converse(self, r: str) -> Optional[str]:
        return self.converses.get(r)

    def isup_r(self, r: str) -> bool:
        return r in self.up_relations

    def isdn_r(self, r: str) -> bool:
        return r in self.down_relations

    @staticmethod
    def isquant_r(r: str) -> bool:
        return r in QUANTIFIER_RELATIONS

    def rel_sort_key(self, r: str) -> tuple:
        """Sort key implementing ISLESS.R (converses first, priority relations,
        then alphabetical)."""
        if r in self.up_relations:
            base = self.converses.get(r, r)
            k = self._down_key(base)
            return (0,) + k
        return (1,) + self._down_key(r)

    @staticmethod
    def _down_key(r: str) -> tuple:
        i = _PRIORITY_INDEX.get(r)
        if i is not None:
            return (0, i, "")
        return (1, 0, r)

    # ------------------------------------------------------------------
    # flat cable sets (fcableset)
    def insert_fcs(self, node: Node, r: str, ns: tuple) -> None:
        """INSERT.FCS on NODE's cable set: union NS into relation R."""
        fcs = node.fcableset
        old = fcs.get(r)
        if old is not None:
            fcs[r] = ns_union(old, ns)
            return
        key = self.rel_sort_key(r)
        if not fcs or self.rel_sort_key(next(reversed(fcs))) <= key:
            fcs[r] = ns
            return
        items = list(fcs.items())
        node.fcableset = {}
        inserted = False
        for rel, val in items:
            if not inserted and key < self.rel_sort_key(rel):
                node.fcableset[r] = ns
                inserted = True
            node.fcableset[rel] = val
        if not inserted:
            node.fcableset[r] = ns

    def make_fcs(self, cs: Iterable[tuple[str, tuple]]) -> dict:
        """CS-TO-FCS: a flat cable set (sorted by relation) from a cable set."""
        tmp = Node("", BASE, 0)
        for r, ns in cs:
            self.insert_fcs(tmp, r, ns)
        return tmp.fcableset

    def setnodeset(self, n: Node, r: str, ns: tuple) -> None:
        """SETNODESET.N"""
        if not ns:
            n.fcableset.pop(r, None)
        elif r in n.fcableset:
            n.fcableset[r] = ns
        else:
            self.insert_fcs(n, r, ns)

    def updatenodeset(self, n: Node, r: str, newn: Node) -> None:
        """UPDATENODESET.N: add NEWN to N's R cable."""
        self.insert_fcs(n, r, (newn,))

    def down_fcs(self, n: Node) -> list[tuple[str, tuple]]:
        """The descending cables of N (DOWN.FCS)."""
        items = list(n.fcableset.items())
        for i, (r, _ns) in enumerate(items):
            if r in self.down_relations:
                return items[i:]
        return []

    def up_fcs(self, n: Node) -> list[tuple[str, tuple]]:
        return [(r, ns) for r, ns in n.fcableset.items() if r in self.up_relations]

    def n_to_cs(self, n: Node) -> list[tuple[str, tuple]]:
        return list(n.fcableset.items())

    def n_to_downcs(self, n: Node) -> list[tuple[str, tuple]]:
        return self.down_fcs(n)

    def calcheight(self, n: Node) -> int:
        h = 0
        for _r, ns in self.down_fcs(n):
            for m in ns:
                h = max(h, m.height)
        return h + 1

    def dominatednodes(self, node: Node) -> tuple:
        dominated: tuple = ()
        for _r, ns in self.down_fcs(node):
            dominated = ns_union(ns, dominated)
            for n in ns:
                if not (n.is_base or n.is_var):
                    dominated = ns_union(self.dominatednodes(n), dominated)
        return ns_compl(dominated, node.get_freevars())

    def dominatingnodes(self, node: Node) -> tuple:
        dominating: tuple = ()
        for _r, ns in self.up_fcs(node):
            dominating = ns_union(ns, dominating)
            for n in ns:
                dominating = ns_union(self.dominatingnodes(n), dominating)
        return ns_compl(dominating, self.value_sv("patterns") or ())

    def dominating_asupp_nodes(self, node: Node) -> tuple:
        dominating: tuple = ()
        for _r, ns in self.up_fcs(node):
            for n in ns:
                if n.asupport:
                    dominating = ns_insert(n, dominating)
                if not (n.is_base or n.is_var):
                    dominating = ns_union(self.dominating_asupp_nodes(n), dominating)
        return ns_compl(dominating, node.get_freevars())

    def dominates(self, m1: Node, m2: Node) -> bool:
        for _r, ns in self.down_fcs(m1):
            for n in ns:
                if n is m2 or self.dominates(n, m2):
                    return True
        return False

    def beep(self) -> None:
        """BEEP: sound the terminal bell."""
        self.write("\a")

    # ------------------------------------------------------------------
    # nodes (node2)
    def node(self, ident: Any) -> Optional[Node]:
        """NODE: the node with identifier IDENT, or None."""
        if isinstance(ident, Node):
            return ident
        if isinstance(ident, (list, tuple)):
            if not ident:
                return None
            ident = ident[0]
            if isinstance(ident, Node):
                return ident
        return self.nodes_by_name.get(self.node_name(ident))

    def snepsul_node(self, name: str) -> Optional[Node]:
        """The node a SNePSUL expression refers to by NAME.  Generated names
        (M1, V2, ...) are upper case; lower-case m1 also finds M1, so the
        names of the original SNePS documentation and demos work.  Not used
        for SNePSLOG, where p3 is a predicate and never the pattern node P3."""
        n = self.nodes_by_name.get(name)
        if n is None and not getattr(self, "snepslog_running", False) \
                and _GENERATED_NAME.match(name):
            n = self.nodes_by_name.get(name.upper())
        return n

    @staticmethod
    def node_name(ident: Any) -> str:
        if isinstance(ident, str):
            return ident
        if isinstance(ident, (int, float)) or type(ident).__name__ == "Fraction":
            return number_name(ident)
        name = getattr(ident, "name", None)
        if isinstance(name, str):
            return name
        if ident is None:
            return "nil"
        if ident is True:
            return "t"
        raise SNePSError(f"Function node called with {ident!r}, which is neither a node, "
                         "a symbol, a number, nor a string.", "sneps", "node")

    def _next_order(self) -> int:
        self.node_counter += 1
        return self.node_counter

    def newnode(self, ident: Any, type: str, order: Optional[int] = None) -> Optional[Node]:
        name = self.node_name(ident)
        if name in self.nodes_by_name:
            return None
        n = Node(name, type, order if order is not None else self._next_order(), True, self)
        self.nodes_by_name[name] = n
        self.sv_add("nodes", n)
        return n

    def newtempnode(self, ident: Any, type: str) -> Node:
        return Node(self.node_name(ident), type, self._next_order(), False, self)

    def newpbase(self, ident: Any) -> Optional[Node]:
        return self.newnode(ident, BASE)

    def gennewnode(self, prefix: str, type: str) -> Node:
        if prefix in _TEMP_PREFIXES:
            self.id_counters[prefix] += 1
            return self.newtempnode(f"{prefix.upper()}{self.id_counters[prefix]}", type)
        while True:
            self.id_counters[prefix] += 1
            n = self.newnode(f"{prefix.upper()}{self.id_counters[prefix]}", type)
            if n is not None:
                return n

    def genpbase(self) -> Node:
        return self.gennewnode("b", BASE)

    def genpmol(self) -> Node:
        return self.gennewnode("m", MOL)

    def genpvar(self) -> Node:
        v = self.gennewnode("v", VAR)
        self.sv_add("varnodes", v)
        return v

    def genppat(self) -> Node:
        p = self.gennewnode("p", PAT)
        self.sv_add("patterns", p)
        return p

    def gentmol(self) -> Node:
        return self.gennewnode("tm", MOL)

    def gentvar(self) -> Node:
        return self.gennewnode("tv", VAR)

    def gentpat(self) -> Node:
        return self.gennewnode("tp", PAT)

    def node_ref(self, name: str) -> Node:
        """N^: the node named NAME, created (typed by its name) if needed."""
        return self.node(name) or self.newnode(name, symbol_type(name))  # type: ignore[return-value]

    def fold_name(self, name: str) -> str:
        """NAME with the case folding that ``fold_case`` applies to input."""
        if getattr(self, "fold_case", None) == "lower":
            return name.lower()
        if getattr(self, "fold_case", None) == "upper":
            return name.upper()
        return name

    def value_to_node(self, obj: Any) -> Node:
        """The (possibly new) base node named by OBJ (a name or a number)."""
        if isinstance(obj, Node):
            return obj
        name = self.node_name(obj)
        return self.nodes_by_name.get(name) or self.newpbase(name)  # type: ignore[return-value]

    def values_to_ns(self, objs: Any) -> tuple:
        if not isinstance(objs, (list, tuple)):
            objs = [objs]
        ns: tuple = ()
        for o in objs:
            ns = ns_insert(self.value_to_node(o), ns)
        return ns

    def all_nodes(self) -> tuple:
        return self.value_sv("nodes") or ()

    # ------------------------------------------------------------------
    # contexts (context2)
    def get_context(self, c: Any) -> Optional[Context]:
        if isinstance(c, Context):
            return c
        if self.is_sv(c):
            v = self.value_sv(c)
            return v if isinstance(v, Context) else None
        return None

    def current_context(self, cntx: Any = None) -> Optional[Context]:
        """The context designated by CNTX, or by the current context."""
        c = cntx if cntx is not None else self.crntct
        if isinstance(c, Context):
            return c
        return self.get_context(c)

    def getcontext(self, hyps: tuple) -> Optional[Context]:
        return self.contexts.get(tuple(hyps))

    def newcontext(self, order: int, hyps: tuple) -> Context:
        ct = Context(order, tuple(hyps))
        self.contexts[ct.hyps] = ct
        for n in ct.hyps:
            n.contexts = cts_insert(ct, n.contexts)
        return ct

    def gennewcontext(self, hyps: tuple) -> Context:
        self.context_counter += 1
        return self.newcontext(self.context_counter, hyps)

    def buildcontext(self, hyps: tuple) -> Context:
        return self.getcontext(hyps) or self.gennewcontext(tuple(hyps))

    def make_hyp_set(self, hyps: tuple, cts: Iterable[Context]) -> tuple:
        out = hyps
        for c in reversed(list(cts)):
            out = ns_union(c.hyps, out)
        return out

    def fullbuildcontext(self, hyps: tuple, cts: Iterable[Context] = ()) -> Context:
        hs = self.make_hyp_set(tuple(hyps), cts)
        ct = self.getcontext(hs)
        if ct is None:
            ct = self.buildcontext(hs)
            self.isinconsis_ct(ct)
        return ct

    def isinconsis_ct(self, c: Context) -> bool:
        if c.kinconsistent:
            return True
        for ng in self.nogoods:
            if ns_issubset(ng, c.hyps):
                c.kinconsistent = True
                return True
        return False

    def isokinconsis_ct(self, c: Context) -> bool:
        if c.okinconsistent:
            return True
        for ng in self.oknogoods:
            if ns_issubset(ng, c.hyps):
                c.okinconsistent = True
                return True
        return False

    def record_inconsistent(self, hyps: tuple) -> None:
        for sup in self.nogoods:
            if ns_issubset(hyps, sup):
                self.nogoods.remove(sup)
                break
        self.nogoods.insert(0, tuple(hyps))

    def record_ok_inconsistent(self, hyps: tuple) -> None:
        for sup in self.oknogoods:
            if ns_issubset(hyps, sup):
                self.oknogoods.remove(sup)
                break
        self.oknogoods.insert(0, tuple(hyps))

    def update_contexts(self, cts1: Iterable[Context], cts2: Iterable[Context]) -> None:
        """Record that every context of CTS1 is inconsistent with every one of CTS2."""
        cts2 = list(cts2)
        for c1 in cts1:
            for c2 in cts2:
                u = ns_union(c1.hyps, c2.hyps)
                if not any(ns_issubset(ng, u) for ng in self.nogoods):
                    self.record_inconsistent(u)

    def ok_update_contexts(self, cts1: Iterable[Context], cts2: Iterable[Context]) -> None:
        cts2 = list(cts2)
        for c1 in cts1:
            for c2 in cts2:
                u = ns_union(c1.hyps, c2.hyps)
                if not any(ns_issubset(ng, u) for ng in self.oknogoods):
                    self.record_ok_inconsistent(u)

    def name_ct(self, ct: Context, name: str) -> Context:
        self.set_sv(name, ct)
        if name not in ct.names:
            ct.names = (name,) + ct.names
        return ct

    def removename_ct(self, ct: Context, name: str) -> Context:
        ct.names = tuple(x for x in ct.names if x != name)
        return ct

    @staticmethod
    def issubset_ct(c1: Context, c2: Context) -> bool:
        return ns_issubset(c1.hyps, c2.hyps)

    def allct(self) -> tuple:
        return tuple(sorted(self.contexts.values(), key=lambda c: -c.order))

    # ------------------------------------------------------------------
    # assertion (context3)
    def assert_n(self, n: Node, crntname: Any = None) -> None:
        """ASSERT.N: make N a hypothesis of the context named CRNTNAME."""
        if crntname is None:
            crntname = self.crntct
        ct = self.get_context(crntname)
        newassrt = self.buildcontext((n,))
        newct = self.fullbuildcontext((n,), (ct,) if ct is not None else ())
        n.asupport = ctcs_insert("hyp", newassrt, n.asupport)
        if isinstance(crntname, str):
            self.name_ct(newct, crntname)
        if self.isinconsis_ct(newct) and self.isokinconsis_ct(newct):
            if self.infertrace:
                self.write("The context named %s is inconsistent.\n" % _english_list(newct.names))
        else:
            self.ck_contradiction(n, newct, "assertion")

    def ck_contradiction(self, n: Node, ct: Context, flag: str) -> Any:
        """Hook for SNeBR (overridden by the belief revision mixin)."""
        return None

    def isassert(self, n: Node, cntx: Any = None) -> bool:
        """ISASSERT.N: is N believed in the given (or current) context?"""
        if not n.asupport:
            return False
        ct = self.current_context(cntx)
        if ct is None:
            return False
        hyps = ct.hyps
        for ot in ("hyp", "der", "ext"):
            for c in ctcs_get(ot, n.asupport):
                if ns_issubset(c.hyps, hyps):
                    return True
        return False

    def remove_hyp_itself(self, n: Node, cts: Iterable[Context]) -> tuple:
        out: tuple = ()
        for ct in cts:
            out = cts_insert(self.fullbuildcontext(ns_compl(ct.hyps, (n,))), out)
        return out

    def copy_assertion_state(self, oldnode: Node, newnode: Node) -> Node:
        if self.isassert(oldnode):
            self.addsupport(ctcs_filter(oldnode.asupport, self.current_context()), newnode)
        return newnode

    def addsupport(self, ctcs: tuple, n: Node) -> None:  # pragma: no cover - replaced by SNIP
        for ot, cts in ctcs:
            for c in cts:
                n.asupport = ctcs_insert(ot, c, n.asupport)


def _english_list(items: Iterable[Any]) -> str:
    """FORMAT ~{~A~#[~;, and ~:;, ~]~}"""
    items = [str(x) for x in items]
    if not items:
        return ""
    out = []
    for i, x in enumerate(items):
        out.append(x)
        rest = len(items) - i - 1
        if rest == 1:
            out.append(", and ")
        elif rest > 1:
            out.append(", ")
    return "".join(out)
