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
"""Saving and restoring networks as JSON (sneps.io.serialize)."""

from __future__ import annotations

import json

from sneps import Network
from sneps.io import serialize


def knowledge_base() -> Network:
    net = Network(output=False)
    net.tell("Man(Socrates).\nMan(Plato).\nall(x)(Man(x) => Mortal(x)).")
    net.ask("Mortal(Socrates)")
    return net


def summary(net: Network) -> list:
    return [(n.name, n.type, n.order, net.isassert(n),
             [(r, [m.name for m in ns]) for r, ns in net.down_fcs(n)])
            for n in sorted(net.all_nodes(), key=lambda n: n.order)]


def test_round_trip_through_a_dict():
    net = knowledge_base()
    data = serialize.to_dict(net)
    json.dumps(data)  # JSON-compatible
    copy = serialize.from_dict(Network(output=False), data)
    assert summary(copy) == summary(net)
    assert [c.order for c in copy.contexts.values()] == [c.order for c in net.contexts.values()]


def test_round_trip_through_a_file(tmp_path):
    net = knowledge_base()
    path = tmp_path / "kb.json"
    serialize.save(net, str(path))
    copy = serialize.load(str(path))
    assert summary(copy) == summary(net)


def test_restored_network_keeps_reasoning():
    copy = serialize.from_dict(Network(output=False), serialize.to_dict(knowledge_base()))
    assert [copy.node_text(n) for n in copy.ask("Mortal(Plato)")] == ["Mortal(Plato)"]
    new = copy.tell("Man(Aristotle).")
    assert new[0].name not in {n.name for n in knowledge_base().all_nodes()}
