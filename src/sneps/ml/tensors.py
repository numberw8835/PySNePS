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
"""The network as arrays: edge lists, sparse adjacency and node features.

:func:`to_tensors` returns a :class:`GraphTensors` holding numpy arrays in the
layout used by graph-learning libraries (an ``edge_index`` of shape ``2 x E``
plus an ``edge_type`` per edge, as for relational GNNs such as R-GCN), which
converts to scipy sparse matrices, torch tensors, or a dictionary that can be
passed straight to ``torch_geometric.data.Data(**d)``.

Node feature columns (:data:`BASIC_FEATURES`, in order):

=================  ===========================================================
``is_base``        1 for base nodes (individuals, constants)
``is_mol``         1 for molecular nodes (propositions, acts, ...)
``is_pat``         1 for pattern nodes (open propositions with free variables)
``is_var``         1 for variable nodes
``asserted``       1 if the node is believed in the export context
``hypothesis``     1 if the node is a hypothesis of that context
``is_rule``        1 for rule nodes (entailments, and-or, thresh, ...)
``is_negation``    1 for negations (``min 0 max 0`` with a single argument)
``height``         the node's height (0 for atomic nodes)
``out_degree``     number of descending arcs from the node
``in_degree``      number of descending arcs into the node
``num_relations``  number of distinct relations on its descending arcs
``num_supports``   number of contexts in its assertion support
=================  ===========================================================

With ``relation_counts=True`` two columns per relation follow:
``out:<relation>`` and ``in:<relation>``, the number of arcs with that
relation leaving and entering the node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..core.node import Node
from ._deps import require
from .graph import (NODE_TYPES, arcs, believed_closure, context_label, is_hypothesis,
                    resolve_context, select_nodes)

BASIC_FEATURES = ("is_base", "is_mol", "is_pat", "is_var", "asserted", "hypothesis",
                  "is_rule", "is_negation", "height", "out_degree", "in_degree",
                  "num_relations", "num_supports")


@dataclass
class GraphTensors:
    """Array view of a network (see the module documentation)."""

    node_names: list[str]
    relations: list[str]
    edge_index: Any            # int64 array, shape (2, E): row 0 heads, row 1 tails
    edge_type: Any             # int64 array, shape (E,): index into RELATIONS
    x: Any                     # float array, shape (N, F): node features
    feature_names: list[str]
    node_type: Any             # int64 array, shape (N,): index into NODE_TYPES
    asserted: Any              # bool array, shape (N,)
    context: Optional[str] = None
    node_index: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.node_index:
            self.node_index = {n: i for i, n in enumerate(self.node_names)}

    @property
    def num_nodes(self) -> int:
        return len(self.node_names)

    @property
    def num_edges(self) -> int:
        return int(self.edge_index.shape[1])

    @property
    def num_relations(self) -> int:
        return len(self.relations)

    def adjacency(self, relation: Optional[str] = None, symmetric: bool = False) -> Any:
        """A ``scipy.sparse.csr_matrix`` (N x N) counting the arcs of RELATION
        (all relations if None) from row node to column node."""
        sp = require("scipy.sparse", "GraphTensors.adjacency")
        np = require("numpy", "GraphTensors.adjacency")
        if relation is None:
            mask = np.ones(self.num_edges, dtype=bool)
        else:
            if relation not in self.relations:
                raise KeyError(relation)
            mask = self.edge_type == self.relations.index(relation)
        rows, cols = self.edge_index[0][mask], self.edge_index[1][mask]
        if symmetric:
            rows, cols = np.concatenate([rows, cols]), np.concatenate([cols, rows])
        data = np.ones(len(rows), dtype=np.float32)
        n = self.num_nodes
        return sp.csr_matrix((data, (rows, cols)), shape=(n, n))

    def adjacency_by_relation(self) -> dict:
        """One sparse adjacency matrix per relation."""
        return {r: self.adjacency(r) for r in self.relations}

    def to_torch(self, device: Any = None) -> dict:
        """The arrays as torch tensors (``x``, ``edge_index``, ``edge_type``,
        ``node_type``, ``asserted``)."""
        torch = require("torch", "GraphTensors.to_torch")
        return {
            "x": torch.as_tensor(self.x, device=device),
            "edge_index": torch.as_tensor(self.edge_index, device=device),
            "edge_type": torch.as_tensor(self.edge_type, device=device),
            "node_type": torch.as_tensor(self.node_type, device=device),
            "asserted": torch.as_tensor(self.asserted, device=device),
        }

    def to_pyg_dict(self, device: Any = None) -> dict:
        """Keyword arguments for ``torch_geometric.data.Data``: the tensors of
        :meth:`to_torch`, ``y`` (the asserted flag as a class label),
        ``num_nodes``, ``num_relations``, ``node_names`` and ``relations``."""
        d = self.to_torch(device)
        d["y"] = d["asserted"].long()
        d["num_nodes"] = self.num_nodes
        d["num_relations"] = self.num_relations
        d["node_names"] = list(self.node_names)
        d["relations"] = list(self.relations)
        return d


def node_feature_rows(net: Any, nodes: list[Node], ct: Any,
                      down: list[tuple[Node, str, Node]], relations: list[str],
                      relation_counts: bool) -> tuple[list[list[float]], list[str]]:
    """Feature rows (see :data:`BASIC_FEATURES`) for NODES."""
    index = {id(n): i for i, n in enumerate(nodes)}
    out_deg = [0] * len(nodes)
    in_deg = [0] * len(nodes)
    rel_pos = {r: k for k, r in enumerate(relations)}
    out_rel = [[0] * len(relations) for _ in nodes] if relation_counts else []
    in_rel = [[0] * len(relations) for _ in nodes] if relation_counts else []
    for h, r, t in down:
        i, j = index[id(h)], index[id(t)]
        out_deg[i] += 1
        in_deg[j] += 1
        if relation_counts:
            out_rel[i][rel_pos[r]] += 1
            in_rel[j][rel_pos[r]] += 1
    rows = []
    for i, n in enumerate(nodes):
        molish = n.is_mol or n.is_pat
        row = [float(n.is_base), float(n.is_mol), float(n.is_pat), float(n.is_var),
               float(ct is not None and net.isassert(n, ct)), float(is_hypothesis(n, ct)),
               float(molish and n.is_rule()), float(molish and n.is_not()),
               float(n.height), float(out_deg[i]), float(in_deg[i]),
               float(len(net.down_fcs(n))), float(sum(len(cts) for _ot, cts in n.asupport))]
        if relation_counts:
            row.extend(float(v) for v in out_rel[i])
            row.extend(float(v) for v in in_rel[i])
        rows.append(row)
    names = list(BASIC_FEATURES)
    if relation_counts:
        names += [f"out:{r}" for r in relations] + [f"in:{r}" for r in relations]
    return rows, names


def to_tensors(net: Any, context: Any = None, converse: bool = False,
               relation_counts: bool = False, asserted_only: bool = False,
               include_patterns: bool = True, include_variables: bool = True,
               where: Optional[Callable[[Node], bool]] = None,
               dtype: str = "float32") -> GraphTensors:
    """The network as a :class:`GraphTensors` (numpy arrays).

    Nodes are numbered in creation order and relations in order of first use
    (descending relations before their converses).  CONVERSE adds the
    converse arcs as edges of their own relation types; node degrees always
    count descending arcs only."""
    np = require("numpy", "to_tensors")
    ct = resolve_context(net, context)
    nodes = select_nodes(net, include_patterns, include_variables, where)
    if asserted_only:
        nodes = believed_closure(net, nodes, ct)
    index = {id(n): i for i, n in enumerate(nodes)}
    all_arcs = arcs(net, nodes, converse)
    down = all_arcs if not converse else all_arcs[:len(all_arcs) // 2]
    relations: list[str] = []
    for _h, r, _t in all_arcs:
        if r not in relations:
            relations.append(r)
    rel_index = {r: k for k, r in enumerate(relations)}
    edge_index = np.asarray([[index[id(h)] for h, _r, _t in all_arcs],
                             [index[id(t)] for _h, _r, t in all_arcs]],
                            dtype=np.int64).reshape(2, len(all_arcs))
    edge_type = np.asarray([rel_index[r] for _h, r, _t in all_arcs], dtype=np.int64)
    used_down = {r for _h, r, _t in down}
    down_rels = [r for r in relations if r in used_down]
    rows, names = node_feature_rows(net, nodes, ct, down, down_rels, relation_counts)
    x = np.asarray(rows, dtype=dtype).reshape(len(nodes), len(names))
    node_type = np.asarray([NODE_TYPES.index(n.type) for n in nodes], dtype=np.int64)
    asserted = np.asarray([ct is not None and net.isassert(n, ct) for n in nodes], dtype=bool)
    return GraphTensors([n.name for n in nodes], relations, edge_index, edge_type, x, names,
                        node_type, asserted, context_label(net, context))
