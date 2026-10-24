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
"""Machine-learning exports (sneps.ml)."""

from __future__ import annotations

import csv
import json
import sys

import pytest

from sneps import Network, ml


def knowledge_base() -> Network:
    net = Network(output=False)
    net.tell("Man(Socrates).\nMan(Plato).\nall(x)(Man(x) => Mortal(x)).\n"
             "Loves(Socrates, Plato).")
    net.ask("Mortal(Socrates)")
    return net


# -- triples and vocabularies ---------------------------------------------------

def test_triples_are_the_descending_arcs():
    net = knowledge_base()
    triples = net.triples()
    assert triples[:2] == [("M1", "a1", "Socrates"), ("M1", "r", "Man")]
    assert len(triples) == sum(len(ns) for n in net.all_nodes() for _r, ns in net.down_fcs(n))
    assert all(net.node(h).is_mol or net.node(h).is_pat for h, _r, _t in triples)
    assert net.triples() == triples  # deterministic


def test_converse_triples_mirror_the_descending_ones():
    net = knowledge_base()
    down = net.triples()
    both = net.triples(converse=True)
    assert both[:len(down)] == down
    assert both[len(down):] == [(t, r + "-", h) for h, r, t in down]


def test_asserted_only_keeps_the_believed_structure():
    net = knowledge_base()
    kept = net.triples(asserted_only=True)
    heads = {h for h, _r, _t in kept}
    negation = [n for n in net.all_nodes() if n.is_mol and n.is_not()]
    assert negation and all(n.name not in heads for n in negation)
    assert {"M1", "M2", "M3"} <= heads  # the hypotheses
    assert set(kept) < set(net.triples())


def test_vocabulary_round_trip():
    np = pytest.importorskip("numpy")
    net = knowledge_base()
    vocab = net.vocabulary()
    assert vocab.entities == [n.name for n in sorted(net.all_nodes(), key=lambda n: n.order)]
    ids = vocab.encode(net.triples())
    assert ids.dtype == np.int64 and ids.shape == (len(net.triples()), 3)
    assert vocab.decode(ids) == net.triples()
    assert ml.Vocabulary.from_dict(json.loads(json.dumps(vocab.to_dict()))).entity2id == \
        vocab.entity2id
    small = ml.Vocabulary.from_triples([("a", "r", "b"), ("b", "s", "c")])
    assert small.entities == ["a", "b", "c"] and small.relations == ["r", "s"]


# -- graphs and tensors ---------------------------------------------------------

def test_to_networkx():
    pytest.importorskip("networkx")
    net = knowledge_base()
    g = net.to_networkx(text=True)
    assert g.number_of_nodes() == len(net.all_nodes())
    assert sorted((h, d["relation"], t) for h, t, d in g.edges(data=True)) == \
        sorted(net.triples())
    m1 = g.nodes["M1"]
    assert m1["type"] == "mol" and m1["asserted"] and m1["hypothesis"]
    assert m1["text"] == "Man(Socrates)" and m1["wff"] == "wff1"
    assert m1["description"] == "(M1 (a1 Socrates) (r Man))"
    assert g.nodes["Socrates"]["type"] == "base"
    derived = [n for n, d in g.nodes(data=True) if d.get("text") == "Mortal(Socrates)"]
    assert derived and g.nodes[derived[0]]["asserted"] and not g.nodes[derived[0]]["hypothesis"]
    assert net.to_networkx(converse=True).number_of_edges() == 2 * g.number_of_edges()


def test_to_tensors():
    np = pytest.importorskip("numpy")
    net = knowledge_base()
    t = net.to_tensors(converse=True, relation_counts=True)
    n, e = len(net.all_nodes()), 2 * len(net.triples())
    assert t.num_nodes == n and t.num_edges == e
    assert t.edge_index.shape == (2, e) and t.edge_index.dtype == np.int64
    assert t.edge_type.shape == (e,) and t.edge_type.max() < t.num_relations
    assert t.x.shape == (n, len(t.feature_names))
    assert t.feature_names[:len(ml.BASIC_FEATURES)] == list(ml.BASIC_FEATURES)
    col = {name: k for k, name in enumerate(t.feature_names)}
    i = t.node_index["M1"]
    assert t.x[i, col["is_mol"]] == 1 and t.x[i, col["asserted"]] == 1
    assert t.x[i, col["out_degree"]] == 2 and t.x[i, col["out:a1"]] == 1
    assert t.x[t.node_index["Socrates"], col["in:a1"]] >= 1
    assert list(t.asserted) == [net.isassert(net.node(name)) for name in t.node_names]
    assert net.vocabulary(converse=True).relations == t.relations


def test_sparse_adjacency():
    pytest.importorskip("scipy")
    net = knowledge_base()
    t = net.to_tensors()
    a = t.adjacency()
    assert a.shape == (t.num_nodes, t.num_nodes) and a.sum() == t.num_edges
    per = t.adjacency_by_relation()
    assert set(per) == set(t.relations)
    assert sum(m.sum() for m in per.values()) == t.num_edges
    r = per["r"]
    assert r[t.node_index["M1"], t.node_index["Man"]] == 1


def test_torch_and_pyg_dicts():
    torch = pytest.importorskip("torch")
    net = knowledge_base()
    t = net.to_tensors()
    d = t.to_torch()
    assert d["edge_index"].dtype == torch.int64 and d["x"].dtype == torch.float32
    pyg = t.to_pyg_dict()
    assert pyg["num_nodes"] == t.num_nodes and pyg["y"].dtype == torch.int64
    assert pyg["node_names"] == t.node_names


def test_missing_optional_dependency_is_explained(monkeypatch):
    monkeypatch.setitem(sys.modules, "networkx", None)
    with pytest.raises(ImportError, match=r"pysneps\[ml\]"):
        knowledge_base().to_networkx()


# -- propositions and facts -------------------------------------------------------

def test_propositions():
    net = knowledge_base()
    props = {p["text"]: p for p in net.propositions()}
    man = props["Man(Socrates)"]
    assert man["asserted"] and man["hypothesis"] and man["origin"] == "hyp"
    assert man["cables"] == {"a1": ["Socrates"], "r": ["Man"]}
    assert man["predicate"] == "Man" and man["args"] == [["Socrates"]]
    mortal = props["Mortal(Socrates)"]
    assert mortal["asserted"] and mortal["origin"] == "der" and not mortal["hypothesis"]
    rule = props["all(x)(Man(x) => Mortal(x))"]
    assert rule["is_rule"] and rule["predicate"] is None
    assert any(p["is_negation"] and not p["asserted"] for p in props.values())
    json.dumps(list(props.values()))


@pytest.mark.parametrize("mode", [1, 2, 3])
def test_facts_follow_the_snepslog_case_frames(mode):
    net = Network(output=False)
    if mode == 3:
        net.tell("set-mode-3\ndefine-frame Loves(nil lover loved)\n"
                 "define-frame Man(nil member)")
    else:
        net.tell(f"set-mode-{mode}")
    net.tell("Loves(Romeo, Juliet).\nMan(Romeo).")
    assert [(f["predicate"], f["args"]) for f in net.facts()] == \
        [("Loves", ["Romeo", "Juliet"]), ("Man", ["Romeo"])]
    assert net.fact_triples() == [("Romeo", "Loves", "Juliet")]


def test_facts_of_snepsul_case_frames():
    net = Network(output=False)
    net.run_snepsul("(define member class)\n(assert member Socrates class man)")
    assert net.facts() == [{"node": "M1", "predicate": "class|member",
                            "args": ["man", "Socrates"], "asserted": True}]


def test_exports_leave_snepslog_output_unchanged():
    def session(export: bool) -> str:
        net = knowledge_base()
        if export:
            net.propositions()
            ml.graph.node_texts(net, net.all_nodes())
        net.tell("Man(Aristotle).")
        return net.snepslog_string(net.ask("Mortal(Aristotle)")) + \
            net.snepslog_string(list(net.all_nodes()))
    assert session(True) == session(False)


# -- datasets -----------------------------------------------------------------------

def test_split_is_deterministic_and_covers_entities():
    triples = [(f"e{i}", f"r{i % 3}", f"e{(i * 7) % 20}") for i in range(60)]
    a = ml.split_triples(triples, seed=3)
    b = ml.split_triples(triples, seed=3)
    assert (a.train, a.valid, a.test) == (b.train, b.valid, b.test)
    train, valid, test = a
    assert sorted(train + valid + test) == sorted(set(triples))
    seen = {e for h, _r, t in train for e in (h, t)}
    assert all(h in seen and t in seen for h, _r, t in valid + test)
    assert ml.split_triples(triples, seed=4).train != a.train


def test_negative_triples_avoid_known_triples():
    triples = [("a", "r", "b"), ("b", "r", "c"), ("c", "r", "a")]
    neg = ml.negative_triples(triples, num=2, seed=0)
    assert neg and not set(neg) & set(triples)
    assert all(r == "r" for _h, r, _t in neg)
    assert ml.negative_triples(triples, num=2, seed=0) == neg
    tails = ml.negative_triples(triples, num=1, corrupt="tail", seed=1)
    assert [h for h, _r, _t in tails] == [h for h, _r, _t in triples][:len(tails)]


def test_from_triples_rebuilds_the_network():
    net = knowledge_base()
    triples = net.triples()
    copy, mapping = ml.from_triples(triples, types=ml.node_types(net), return_mapping=True)
    rebuilt = {(mapping[h].name, r, mapping[t].name) for h, r, t in triples}
    assert rebuilt == set(copy.triples())
    assert copy.node("V1").is_var and copy.node("P1").is_pat


def test_networks_from_triples_with_assertions():
    net = Network.from_triples([("M1", "member", "Socrates"), ("M1", "class", "man")],
                               assert_nodes=True)
    m1 = net.node("M1")
    assert net.isassert(m1) and [r for r, _ns in net.down_fcs(m1)] == ["class", "member"]
    mapping = net.add_triples([("X", "member", "Plato"), ("X", "class", "man")])
    assert mapping["X"].name == "M2" and not net.isassert(mapping["X"])


def test_export_dataset(tmp_path):
    net = knowledge_base()
    paths = net.export_dataset(str(tmp_path / "ds"), seed=1)
    meta = json.loads(open(paths["metadata.json"]).read())
    parts = [ml.read_triples(paths[f"{k}.tsv"]) for k in ("train", "valid", "test")]
    assert sorted(sum(parts, [])) == sorted(ml.read_triples(paths["triples.tsv"]))
    assert meta["counts"]["triples"] == len(net.triples())
    assert meta["counts"]["entities"] == len(open(paths["entities.txt"]).read().split("\n")) - 1
    props = ml.read_jsonl(paths["propositions.jsonl"])
    assert len(props) == sum(1 for n in net.all_nodes() if n.is_mol)
    facts = net.export_dataset(str(tmp_path / "facts"), kind="facts")
    assert ml.read_triples(facts["triples.tsv"]) == net.fact_triples(asserted_only=False)


def test_csv_and_jsonl(tmp_path):
    rows = [{"node": "M1", "cables": {"r": ["Man"]}, "asserted": True},
            {"node": "M2", "cables": {}, "asserted": False}]
    ml.write_jsonl(rows, str(tmp_path / "rows.jsonl"))
    assert ml.read_jsonl(str(tmp_path / "rows.jsonl")) == rows
    ml.write_csv(rows, str(tmp_path / "rows.csv"))
    with open(tmp_path / "rows.csv", newline="") as fh:
        back = list(csv.DictReader(fh))
    assert back[0]["node"] == "M1" and json.loads(back[0]["cables"]) == {"r": ["Man"]}


def test_empty_network():
    net = Network(output=False)
    assert net.triples() == [] and net.propositions() == [] and net.facts() == []
    pytest.importorskip("numpy")
    t = net.to_tensors()
    assert t.edge_index.shape == (2, 0) and t.x.shape == (0, len(ml.BASIC_FEATURES))
