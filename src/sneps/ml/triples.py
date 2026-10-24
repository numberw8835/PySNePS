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
"""Arc triples, integer vocabularies, and building networks from triples.

An *arc triple* ``(head, relation, tail)`` names one arc of the network, e.g.
``("M1", "member", "Socrates")``.  The arc triples of a network describe it
completely (up to the names of its molecular nodes), so :func:`from_triples`
can rebuild it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from ..core.node import BASE, MOL, PAT, VAR, Node
from ..core.nodeset import ns_make
from ._deps import require
from .graph import arcs, believed_closure, resolve_context, select_nodes

Triple = tuple[str, str, str]


def triples(net: Any, context: Any = None, converse: bool = False, asserted_only: bool = False,
            include_patterns: bool = True, include_variables: bool = True,
            where: Optional[Callable[[Node], bool]] = None) -> list[Triple]:
    """The arcs of NET as ``(head, relation, tail)`` node-name triples.

    Descending arcs come first, heads in creation order; CONVERSE appends the
    converse arcs (``("Socrates", "member-", "M1")``).  ASSERTED_ONLY keeps the
    arcs of the propositions asserted in CONTEXT (default: the current
    context) and of the nodes they dominate."""
    nodes = select_nodes(net, include_patterns, include_variables, where)
    if asserted_only:
        nodes = believed_closure(net, nodes, resolve_context(net, context))
    return [(h.name, r, t.name) for h, r, t in arcs(net, nodes, converse)]


@dataclass
class Vocabulary:
    """Integer ids for entity (node) names and relation names.

    ``entity2id``/``relation2id`` map names to ids and ``entities``/
    ``relations`` (also available as ``id2entity``/``id2relation``) map ids
    back to names."""

    entities: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entities = list(self.entities)
        self.relations = list(self.relations)
        self.entity2id = {e: i for i, e in enumerate(self.entities)}
        self.relation2id = {r: i for i, r in enumerate(self.relations)}
        if len(self.entity2id) != len(self.entities) or \
                len(self.relation2id) != len(self.relations):
            raise ValueError("duplicate names in vocabulary")

    # -- construction ---------------------------------------------------------
    @classmethod
    def from_triples(cls, triples: Iterable[Sequence[str]]) -> "Vocabulary":
        """Names in order of first appearance in TRIPLES."""
        ents: dict[str, None] = {}
        rels: dict[str, None] = {}
        for h, r, t in triples:
            ents.setdefault(h)
            rels.setdefault(r)
            ents.setdefault(t)
        return cls(list(ents), list(rels))

    @classmethod
    def from_network(cls, net: Any, converse: bool = False, include_patterns: bool = True,
                     include_variables: bool = True,
                     all_relations: bool = False) -> "Vocabulary":
        """Every node of NET in creation order, and the relations of its arcs
        in order of first use, followed by their converses if CONVERSE (the
        numbering :func:`~sneps.ml.to_tensors` uses).  ALL_RELATIONS also
        includes the defined relations no arc uses."""
        nodes = select_nodes(net, include_patterns, include_variables)
        rels: dict[str, None] = {}
        for _h, r, _t in arcs(net, nodes, False):
            rels.setdefault(r)
        if all_relations:
            for r in reversed(net.value_sv("relations") or []):
                if net.isdn_r(r):
                    rels.setdefault(r)
        if converse:
            for r in list(rels):
                rels.setdefault(net.converse(r) or r + "-")
        return cls([n.name for n in nodes], list(rels))

    # -- access ---------------------------------------------------------------
    @property
    def id2entity(self) -> list[str]:
        return self.entities

    @property
    def id2relation(self) -> list[str]:
        return self.relations

    @property
    def num_entities(self) -> int:
        return len(self.entities)

    @property
    def num_relations(self) -> int:
        return len(self.relations)

    def add_entity(self, name: str) -> int:
        i = self.entity2id.get(name)
        if i is None:
            i = self.entity2id[name] = len(self.entities)
            self.entities.append(name)
        return i

    def add_relation(self, name: str) -> int:
        i = self.relation2id.get(name)
        if i is None:
            i = self.relation2id[name] = len(self.relations)
            self.relations.append(name)
        return i

    # -- encoding -------------------------------------------------------------
    def encode_list(self, triples: Iterable[Sequence[str]]) -> list[tuple[int, int, int]]:
        """TRIPLES as ``(head_id, relation_id, tail_id)`` tuples."""
        e, r = self.entity2id, self.relation2id
        return [(e[h], r[rel], e[t]) for h, rel, t in triples]

    def encode(self, triples: Iterable[Sequence[str]]) -> Any:
        """TRIPLES as an ``int64`` numpy array of shape ``(n, 3)`` (h, r, t)."""
        np = require("numpy", "Vocabulary.encode")
        rows = self.encode_list(triples)
        return np.asarray(rows, dtype=np.int64).reshape(len(rows), 3)

    def decode(self, rows: Iterable[Sequence[int]]) -> list[Triple]:
        """Id triples (a list or an ``(n, 3)`` array) back to name triples."""
        return [(self.entities[int(h)], self.relations[int(r)], self.entities[int(t)])
                for h, r, t in rows]

    # -- persistence ----------------------------------------------------------
    def to_dict(self) -> dict:
        return {"entities": list(self.entities), "relations": list(self.relations)}

    @classmethod
    def from_dict(cls, data: Mapping) -> "Vocabulary":
        return cls(data["entities"], data["relations"])


def vocabulary(net: Any, **kw: Any) -> Vocabulary:
    return Vocabulary.from_network(net, **kw)


# -- building networks from triples ------------------------------------------

def from_triples(triples: Iterable[Sequence[str]], net: Any = None,
                 types: Optional[Mapping[str, str]] = None,
                 assert_nodes: Any = None, context: Any = None,
                 return_mapping: bool = False) -> Any:
    """Build the network described by arc TRIPLES (into NET, or a new network).

    Each name that is the head of a descending arc becomes a molecular node
    (a pattern node if it dominates variables) whose cables are its arcs.  The
    other names become base nodes, except that names in a quantifier cable
    (``forall``, ``exists``, ``pevb``) become variable nodes; TYPES (a mapping
    from name to ``"base"``/``"var"``, e.g. :func:`node_types` of the source
    network) overrides this, which matters for free variables.  Converse
    triples (``r-``) are skipped since they are implied, and undefined
    relations are defined.  Nodes are found or built as by SNePSUL ``build``,
    so existing nodes are reused and new molecular nodes get fresh ``M``
    names.

    ASSERT_NODES asserts the given head names (or every molecular head, if
    True) in CONTEXT (default: the current context); contradictions go to
    SNeBR as for any assertion.  Returns the network, or with RETURN_MAPPING
    ``(network, {name: node})``."""
    if net is None:
        from ..network import Network
        net = Network(output=False)
    types = dict(types or {})
    cables: dict[str, dict[str, list[str]]] = {}
    for h, r, t in triples:
        if r.endswith("-") and not net.isdn_r(r):
            continue
        if not net.is_r(r):
            net.new_r(r)
        if net.isquant_r(r):
            types.setdefault(t, VAR)
        cables.setdefault(h, {}).setdefault(r, [])
        if t not in cables[h][r]:
            cables[h][r].append(t)
    mapping: dict[str, Node] = {}
    visiting: set[str] = set()

    def get(name: str) -> Node:
        n = mapping.get(name)
        if n is not None:
            return n
        if name not in cables:
            n = _leaf(net, name, types.get(name))
        else:
            if name in visiting:
                raise ValueError(f"cyclic triples through {name!r}")
            visiting.add(name)
            cs = [(r, ns_make(get(t) for t in ts)) for r, ts in cables[name].items()]
            visiting.discard(name)
            n = net.find_or_build(cs)[0]
        mapping[name] = n
        return n

    for name in cables:
        get(name)
    if assert_nodes:
        if assert_nodes is True:
            heads = [mapping[h] for h in cables if mapping[h].is_mol]
        else:
            heads = [mapping[h] for h in assert_nodes]
        ctname = context if context is not None else net.crntct
        net.assert_nodes(ns_make(heads), ctname)
    return (net, mapping) if return_mapping else net


def node_types(net: Any) -> dict[str, str]:
    """Each node's name mapped to its type, for :func:`from_triples`."""
    return {n.name: n.type for n in net.all_nodes()}


def _leaf(net: Any, name: str, kind: Optional[str]) -> Node:
    n = net.node(name)
    if n is not None:
        return n
    if kind in (MOL, PAT):
        raise ValueError(f"{name!r} is typed {kind} but has no arcs")
    if kind == VAR:
        n = net.newnode(name, VAR)
        net.sv_add("varnodes", n)
        return n
    if kind not in (None, BASE):
        raise ValueError(f"unknown node type {kind!r} for {name!r}")
    return net.newpbase(name)
