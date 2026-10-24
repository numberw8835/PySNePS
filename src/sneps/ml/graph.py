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
"""The network as a labelled directed graph.

A SNePS network is a graph whose nodes are SNePS nodes and whose edges are
the descending arcs of molecular and pattern nodes: an arc labelled ``member``
from ``M1`` to ``Socrates`` says that ``Socrates`` fills the ``member`` slot of
the proposition ``M1``.  Every descending arc ``r`` has an implicit converse
``r-``; exports include converse arcs only when asked to.

Nodes are always listed in creation order, and arcs in the order SNePS keeps
them, so every export of the same network is identical.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Optional

from ..core.context import Context
from ..core.node import Node
from ..snepslog.generator import m_to_wff
from ._deps import require

NODE_TYPES = ("base", "mol", "pat", "var")


def resolve_context(net: Any, context: Any = None) -> Optional[Context]:
    """The context named or given by CONTEXT (the current context if None)."""
    if isinstance(context, Context):
        return context
    return net.current_context(context)


def context_label(net: Any, context: Any = None) -> Optional[str]:
    if isinstance(context, str):
        return context
    ct = resolve_context(net, context)
    if ct is None:
        return None
    return ct.names[0] if ct.names else repr(ct)


def select_nodes(net: Any, include_patterns: bool = True, include_variables: bool = True,
                 where: Optional[Callable[[Node], bool]] = None) -> list[Node]:
    """The network's nodes in creation order, optionally filtered."""
    out = []
    for n in sorted(net.all_nodes(), key=lambda n: n.order):
        if n.is_pat and not include_patterns:
            continue
        if n.is_var and not include_variables:
            continue
        if where is not None and not where(n):
            continue
        out.append(n)
    return out


def descending_arcs(net: Any, nodes: Iterable[Node]) -> Iterator[tuple[Node, str, Node]]:
    """(head, relation, tail) for every descending arc between NODES."""
    nodes = list(nodes)
    keep = {id(n) for n in nodes}
    for n in nodes:
        for rel, ns in net.down_fcs(n):
            for m in ns:
                if id(m) in keep:
                    yield n, rel, m


def arcs(net: Any, nodes: Iterable[Node], converse: bool = False
         ) -> list[tuple[Node, str, Node]]:
    """The descending arcs between NODES, followed by their converses if asked."""
    down = list(descending_arcs(net, nodes))
    if not converse:
        return down
    up = [(m, net.converse(rel) or rel + "-", n) for n, rel, m in down]
    return down + up


def believed_closure(net: Any, nodes: Iterable[Node], ct: Optional[Context]) -> list[Node]:
    """NODES restricted to those asserted in CT and the nodes they dominate."""
    nodes = list(nodes)
    keep: set[int] = set()
    stack = [n for n in nodes if ct is not None and net.isassert(n, ct)]
    while stack:
        n = stack.pop()
        if id(n) in keep:
            continue
        keep.add(id(n))
        for _rel, ns in net.down_fcs(n):
            stack.extend(ns)
    return [n for n in nodes if id(n) in keep]


def is_hypothesis(n: Node, ct: Optional[Context]) -> bool:
    return ct is not None and any(h is n for h in ct.hyps)


def node_texts(net: Any, nodes: Iterable[Node]) -> dict[int, Optional[str]]:
    """The SNePSLOG text of each molecular or pattern node in NODES.

    Generating text caches SNePSLOG renderings on nodes; the caches are put
    back afterwards so that exporting never changes later SNePSLOG output."""
    gen = getattr(net, "node_text", None)
    out: dict[int, Optional[str]] = {}
    if gen is None:
        return out
    saved = [(n, n.snepslog) for n in net.all_nodes()]
    try:
        for n in nodes:
            if n.is_mol or n.is_pat:
                try:
                    out[id(n)] = gen(n)
                except Exception:
                    out[id(n)] = None
    finally:
        for n, v in saved:
            n.snepslog = v
    return out


def description(net: Any, n: Node) -> str:
    """N as SNePS ``describe`` shows it, with dominated molecular nodes
    expanded and without assertion marks, e.g.
    ``(M2 (forall V1) (ant (P1 (class man) (member V1))) (cq ...))``."""
    if not (n.is_mol or n.is_pat):
        return n.name
    parts = [n.name]
    for rel, ns in net.down_fcs(n):
        parts.append("(" + " ".join([rel] + [description(net, m) for m in ns]) + ")")
    return "(" + " ".join(parts) + ")"


def wff_label(n: Node) -> Optional[str]:
    """The SNePSLOG name of a molecular node (``M3`` is ``wff3``)."""
    return m_to_wff(n) if n.is_mol else None


def node_attributes(net: Any, n: Node, ct: Optional[Context], text: Optional[str] = None,
                    with_text: bool = False) -> dict:
    attrs = {
        "name": n.name,
        "type": n.type,
        "order": n.order,
        "asserted": bool(ct is not None and net.isassert(n, ct)),
        "hypothesis": is_hypothesis(n, ct),
        "height": n.height,
    }
    if n.is_mol or n.is_pat:
        attrs["is_rule"] = bool(n.is_rule())
        attrs["is_negation"] = bool(n.is_not())
        wff = wff_label(n)
        if wff:
            attrs["wff"] = wff
    if with_text and (n.is_mol or n.is_pat):
        attrs["text"] = text or None
        attrs["description"] = description(net, n)
    return attrs


def to_networkx(net: Any, context: Any = None, converse: bool = False, text: bool = False,
                asserted_only: bool = False, include_patterns: bool = True,
                include_variables: bool = True,
                where: Optional[Callable[[Node], bool]] = None) -> Any:
    """The network as a :class:`networkx.MultiDiGraph`.

    Graph nodes are keyed by SNePS node name and carry the attributes ``type``
    (``base``/``mol``/``pat``/``var``), ``order`` (creation order), ``asserted``
    and ``hypothesis`` (in CONTEXT, default the current context), ``height``,
    and for molecular/pattern nodes ``is_rule``, ``is_negation`` and ``wff``;
    with TEXT also their SNePSLOG ``text`` (None if SNePSLOG cannot render the
    case frame) and their SNePSUL ``description`` (see :func:`description`).
    Each arc is an edge keyed and labelled by its ``relation``; with CONVERSE
    every arc ``r`` from ``m`` to ``n`` is matched by an arc ``r-`` from ``n``
    to ``m`` (``converse=True`` on the edge).  ASSERTED_ONLY keeps only the
    asserted nodes and the nodes they dominate (the structure of the believed
    propositions)."""
    nx = require("networkx", "to_networkx")
    ct = resolve_context(net, context)
    nodes = select_nodes(net, include_patterns, include_variables, where)
    if asserted_only:
        nodes = believed_closure(net, nodes, ct)
    texts = node_texts(net, nodes) if text else {}
    g = nx.MultiDiGraph()
    g.graph["context"] = context_label(net, context)
    for n in nodes:
        g.add_node(n.name, **node_attributes(net, n, ct, texts.get(id(n)), text))
    down = list(descending_arcs(net, nodes))
    relations: list[str] = []
    for h, rel, t in down:
        g.add_edge(h.name, t.name, key=rel, relation=rel, converse=False)
        if rel not in relations:
            relations.append(rel)
    if converse:
        for h, rel, t in down:
            conv = net.converse(rel) or rel + "-"
            g.add_edge(t.name, h.name, key=conv, relation=conv, converse=True)
            if conv not in relations:
                relations.append(conv)
    g.graph["relations"] = relations
    return g
