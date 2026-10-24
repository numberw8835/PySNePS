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
"""Machine-learning views of a network (graphs, triples, tensors, datasets).

Everything here is a read-only view computed on demand: nodes are listed in
creation order and arcs in SNePS order, so exports are deterministic.  numpy,
scipy, networkx and torch are optional (``pip install pysneps[ml]`` or
``[torch]``) and imported only by the functions that need them.

:class:`MLMixin` adds the same functions as methods of :class:`sneps.Network`
(``net.triples()``, ``net.to_networkx()``, ``net.to_tensors()``, ...).
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .datasets import (LOGICAL_RELATIONS, Split, export_dataset, fact_triples, facts,
                       negative_triples, propositions, read_jsonl, read_triples, split_triples,
                       write_csv, write_jsonl, write_triples)
from .graph import NODE_TYPES, description, to_networkx
from .tensors import BASIC_FEATURES, GraphTensors, to_tensors
from .triples import Vocabulary, from_triples, node_types, triples, vocabulary

__all__ = [
    "BASIC_FEATURES", "GraphTensors", "LOGICAL_RELATIONS", "MLMixin", "NODE_TYPES", "Split",
    "Vocabulary", "description", "export_dataset", "fact_triples", "facts", "from_triples",
    "negative_triples", "node_types", "propositions", "read_jsonl", "read_triples",
    "split_triples", "to_networkx", "to_tensors", "triples", "vocabulary", "write_csv",
    "write_jsonl", "write_triples",
]


class MLMixin:
    """Machine-learning exports as :class:`~sneps.Network` methods."""

    def to_networkx(self, **kw: Any) -> Any:
        """See :func:`sneps.ml.to_networkx`."""
        return to_networkx(self, **kw)

    def triples(self, **kw: Any) -> list:
        """See :func:`sneps.ml.triples`."""
        return triples(self, **kw)

    def vocabulary(self, **kw: Any) -> Vocabulary:
        """See :meth:`sneps.ml.Vocabulary.from_network`."""
        return Vocabulary.from_network(self, **kw)

    def to_tensors(self, **kw: Any) -> GraphTensors:
        """See :func:`sneps.ml.to_tensors`."""
        return to_tensors(self, **kw)

    def propositions(self, **kw: Any) -> list:
        """See :func:`sneps.ml.propositions`."""
        return propositions(self, **kw)

    def facts(self, **kw: Any) -> list:
        """See :func:`sneps.ml.facts`."""
        return facts(self, **kw)

    def fact_triples(self, **kw: Any) -> list:
        """See :func:`sneps.ml.fact_triples`."""
        return fact_triples(self, **kw)

    def export_dataset(self, directory: str, **kw: Any) -> dict:
        """See :func:`sneps.ml.export_dataset`."""
        return export_dataset(self, directory, **kw)

    def add_triples(self, triples: Iterable[Sequence[str]], **kw: Any) -> dict:
        """Build arc TRIPLES into this network (see :func:`sneps.ml.from_triples`);
        returns the mapping from triple names to nodes."""
        return from_triples(triples, net=self, return_mapping=True, **kw)[1]

    @classmethod
    def from_triples(cls, triples: Iterable[Sequence[str]], **kw: Any) -> Any:
        """A new network built from arc TRIPLES (see :func:`sneps.ml.from_triples`)."""
        return from_triples(triples, net=cls(output=False), **kw)
