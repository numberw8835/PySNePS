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
"""The core SNePS API: building, finding and asserting nodes, contexts,
path-based inference, and independent networks."""

from __future__ import annotations

from sneps import Network


def names(ns) -> list[str]:
    return [n.name for n in ns]


def socrates_net() -> Network:
    net = Network(output=False)
    net.run_snepsul("(define member class subclass superclass)")
    net.run_snepsul("(assert member Socrates class man)")
    return net


def test_assert_creates_believed_molecular_node():
    net = socrates_net()
    m1 = net.node("M1")
    assert m1.is_mol and net.isassert(m1)
    assert names(m1.nodeset("member")) == ["Socrates"]
    assert net.node("Socrates").is_base
    assert [r for r, _ns in net.down_fcs(m1)] == ["class", "member"]


def test_find_and_findassert():
    net = socrates_net()
    net.run_snepsul("(describe (build member Plato class man))")
    m2 = net.node("M2")
    assert m2 is not None and not net.isassert(m2)
    assert set(names(net.run_snepsul("(find class man)"))) == {"M1", "M2"}
    assert names(net.run_snepsul("(findassert class man)")) == ["M1"]
    assert names(net.run_snepsul("(find member Socrates)")) == ["M1"]


def test_building_the_same_proposition_reuses_its_node():
    net = socrates_net()
    again = net.run_snepsul("(assert member Socrates class man)")
    assert again[0] is net.node("M1")
    assert sum(1 for n in net.all_nodes() if n.is_mol) == 1


def test_contexts_separate_beliefs():
    net = socrates_net()
    net.run_snepsul("(set-context () ctx2)")
    net.run_snepsul("(set-default-context ctx2)")
    net.run_snepsul("(assert member Plato class man)")
    m1, m2 = net.node("M1"), net.node("M2")
    assert net.crntct == "ctx2"
    assert net.isassert(m2, "ctx2") and not net.isassert(m1, "ctx2")
    assert net.isassert(m1, "default-defaultct") and not net.isassert(m2, "default-defaultct")


def test_path_based_inference():
    net = socrates_net()
    net.run_snepsul("(assert subclass man superclass animal)")
    net.run_snepsul("(define-path class (compose class (kstar (compose subclass- superclass))))")
    result = net.run_snepsul("(deduce member Socrates class animal)")
    assert len(result) == 1
    m = result[0]
    assert net.isassert(m)
    assert names(m.nodeset("class")) == ["animal"]


def test_networks_are_independent():
    a, b = socrates_net(), Network(output=False)
    assert a.is_r("member") and not b.is_r("member")
    b.run_snepsul("(define member class)")
    b.run_snepsul("(assert member Plato class man)")
    assert names(b.run_snepsul("(find member Plato)")) == ["M1"]
    assert names(a.run_snepsul("(find member Socrates)")) == ["M1"]
    assert a.node("Plato") is None


def test_erase_removes_isolated_nodes():
    net = socrates_net()
    net.run_snepsul("(erase M1)")
    assert net.node("M1") is None
    assert net.node("Socrates") is None
