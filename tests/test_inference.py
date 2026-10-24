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
"""Inference (SNIP) through the SNePSLOG tell/ask interface, belief revision
(SNeBR) in automatic mode, and acting (SNeRE)."""

from __future__ import annotations

from sneps import Network


def test_backward_chaining_through_a_rule():
    net = Network(output=False)
    net.tell("Man(Socrates).\nMan(Plato).\nall(x)(Man(x) => Mortal(x)).")
    result = net.ask("Mortal(Socrates)")
    assert len(result) == 1 and net.isassert(result[0])
    assert net.node_text(result[0]) == "Mortal(Socrates)"
    assert net.askifnot("Mortal(Socrates)") == []
    assert sorted(d["x"].name for d in net.askwh("Mortal(?x)")) == ["Plato", "Socrates"]


def test_unknown_propositions_are_not_derived():
    net = Network(output=False)
    net.tell("all(x)(Man(x) => Mortal(x)).")
    assert net.ask("Mortal(Zeus)") == []


def test_forward_inference():
    net = Network(output=False)
    net.tell("all(x)(Man(x) => Mortal(x)).")
    result = net.tell("Man(Aristotle)!")
    texts = sorted(net.node_text(n) for n in result)
    assert texts == ["Man(Aristotle)", "Mortal(Aristotle)"]
    assert all(net.isassert(n) for n in result)


def test_and_or():
    net = Network(output=False)
    net.tell("andor(1,1){Rich(Bill), Poor(Bill)}.\nRich(Bill).")
    assert net.ask("Poor(Bill)") == []
    assert len(net.askifnot("Poor(Bill)")) == 1


def test_automatic_belief_revision_keeps_the_context_consistent():
    net = Network(output=False)
    net.tell("Rich(Bill).\n~Rich(Bill).")
    believed = bool(net.ask("Rich(Bill)"))
    disbelieved = bool(net.askifnot("Rich(Bill)"))
    assert believed != disbelieved


def test_perform_primitive_and_mental_acts():
    net = Network(output=False)
    net.tell("set-mode-3\ndefine-frame say(action object1)\ndefine-frame Said(nil what)")
    said = []
    net.define_primaction("say", lambda net, act: said.append(
        [n.name for n in act.nodeset("object1")]))
    for action in ("say", "believe", "disbelieve", "snsequence"):
        net.attach_primaction(action, action)
    net.tell("perform say(Hello)")
    assert said == [["Hello"]]
    net.tell("perform snsequence(say(One), believe(Said(Hello)))")
    assert said == [["Hello"], ["One"]]
    assert len(net.ask("Said(Hello)")) == 1
    net.tell("perform disbelieve(Said(Hello))")
    assert net.ask("Said(Hello)") == []


def test_rule_chains_with_names_like_generated_node_names():
    # p3 is a predicate here, never the pattern node P3 that SNePS generates
    net = Network(output=False)
    net.tell("\n".join(f"all(x)(p{i}(x) => p{i + 1}(x))." for i in range(1, 9)) + "\np1(a).")
    assert [net.node_text(n) for n in net.ask("p9(a)")] == ["p9(a)"]
    assert net.node_text(net.ask("p3(a)")[0]) == "p3(a)"


def test_snepsul_finds_generated_nodes_by_lower_case_name():
    net = Network(output=False)
    net.run_snepsul("(define member class) (assert member Socrates class man)")
    assert [n.name for n in net.run_snepsul("(find member Socrates)")] == ["M1"]
    net.run_snepsul("(set-context (m1) solo)")
    assert [h.name for h in net.value_sv("solo").hyps] == ["M1"]
