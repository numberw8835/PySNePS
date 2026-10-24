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
"""Datasets: propositions, facts, link-prediction splits and file formats.

* :func:`propositions` describes every molecular node (its case frame, its
  arguments, whether it is believed and why, its SNePSLOG text), one record
  per proposition, for classification or embedding pipelines.
* :func:`facts` reads atomic propositions as ``predicate(arg, ...)`` facts,
  using the SNePSLOG case frames when there are any, and :func:`fact_triples`
  gives the binary ones as knowledge-graph triples ``(arg1, predicate, arg2)``.
* :func:`split_triples` and :func:`negative_triples` make deterministic
  link-prediction data, and :func:`export_dataset` writes everything to a
  directory.

No third-party package is needed here; files are JSON lines, CSV and TSV.
"""

from __future__ import annotations

import csv
import json
import os
import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Iterator, Optional, Sequence

from ..core.node import Node
from .graph import (context_label, description, is_hypothesis, node_texts, resolve_context,
                    select_nodes, wff_label)
from .triples import Triple, Vocabulary, triples as arc_triples

# Relations of the SNePS logical connectives and quantifiers: propositions
# built with them are rules or compound propositions, not atomic facts.
LOGICAL_RELATIONS = frozenset((
    "forall", "exists", "pevb", "min", "max", "thresh", "threshmax", "emin", "emax", "etot",
    "ant", "&ant", "cq", "dcq", "arg", "default", "vars", "suchthat", "if", "when",
    "whenever", "do"))


# -- propositions --------------------------------------------------------------

def propositions(net: Any, context: Any = None, text: bool = True,
                 include_patterns: bool = False, asserted_only: bool = False,
                 where: Optional[Callable[[Node], bool]] = None) -> list[dict]:
    """One record per molecular node (and pattern node, if asked), in creation
    order, with the keys ``node``, ``wff``, ``type``, ``asserted``,
    ``hypothesis``, ``origin`` (``"hyp"``, ``"der"`` or ``"ext"``: how the
    node is believed in CONTEXT, or None), ``is_rule``, ``is_negation``,
    ``frame`` (its descending relations), ``cables`` (relation -> argument
    names), ``predicate`` and ``args`` (see :func:`facts`; None for compound
    propositions), ``supports`` (the hypothesis sets it is derivable from),
    ``description`` (as SNePS ``describe`` shows it) and, with TEXT, ``text``
    (its SNePSLOG rendering, or None when SNePSLOG cannot render its frame)."""
    ct = resolve_context(net, context)
    nodes = [n for n in select_nodes(net, include_patterns, True, where)
             if n.is_mol or (include_patterns and n.is_pat)]
    if asserted_only:
        nodes = [n for n in nodes if ct is not None and net.isassert(n, ct)]
    texts = node_texts(net, nodes) if text else {}
    out = []
    for n in nodes:
        fact = _fact(net, n)
        rec = {
            "node": n.name,
            "wff": wff_label(n),
            "type": n.type,
            "asserted": bool(ct is not None and net.isassert(n, ct)),
            "hypothesis": is_hypothesis(n, ct),
            "origin": _origin(n, ct),
            "is_rule": bool(n.is_rule()),
            "is_negation": bool(n.is_not()),
            "frame": [r for r, _ns in net.down_fcs(n)],
            "cables": {r: [m.name for m in ns] for r, ns in net.down_fcs(n)},
            "predicate": fact[0] if fact else None,
            "args": fact[1] if fact else None,
            "supports": [{"origin": ot, "hyps": [h.name for h in c.hyps]}
                         for ot, cts in n.asupport for c in cts],
            "description": description(net, n),
        }
        if text:
            rec["text"] = texts.get(id(n)) or None
        out.append(rec)
    return out


def _origin(n: Node, ct: Any) -> Optional[str]:
    if ct is None:
        return None
    hyps = {id(h) for h in ct.hyps}
    for ot in ("hyp", "der", "ext"):
        for tag, cts in n.asupport:
            if tag == ot and any(all(id(h) in hyps for h in c.hyps) for c in cts):
                return ot
    return None


# -- facts ---------------------------------------------------------------------

def _fact(net: Any, n: Node) -> Optional[tuple[str, list[list[str]]]]:
    """``(predicate, [argument names per position])`` for an atomic
    proposition N, or None for compound ones."""
    down = net.down_fcs(n)
    if not down or any(r in LOGICAL_RELATIONS for r, _ns in down):
        return None
    rels = [r for r, _ns in down]

    def names(ns: tuple) -> list[str]:
        return [m.name for m in ns]

    # SNePSLOG mode 1: (r P a1 x1 a2 x2 ...)
    if "r" in rels and len(n.nodeset("r")) == 1:
        args, k = [], 1
        while n.nodeset(f"a{k}"):
            args.append(names(n.nodeset(f"a{k}")))
            k += 1
        if len(rels) == len(args) + 1:
            return n.nodeset("r")[0].name, args
    # SNePSLOG mode 2: (| rel P| P |rel-arg#P1| x1 ...)
    for r in rels:
        if r.startswith(" rel ") and len(n.nodeset(r)) == 1:
            p = r[5:]
            args, k = [], 1
            while n.nodeset(f"rel-arg#{p}{k}"):
                args.append(names(n.nodeset(f"rel-arg#{p}{k}")))
                k += 1
            if len(rels) == len(args) + 1:
                return n.nodeset(r)[0].name, args
    # SNePSLOG mode 3: user-defined case frames
    argsprop = getattr(net, "argsprop", None) or {}
    propargs = getattr(net, "propargs", None) or {}
    cf = tuple(rels)
    choice = argsprop.get(cf)
    if choice is not None:
        if isinstance(choice, list):
            pred = str(choice[0])
            arcs = list(propargs.get(pred, [None]))[1:]
        else:
            pn = n.nodeset(choice)
            pred = pn[0].name if pn else str(choice)
            frame = next((f for f in propargs.values()
                          if f and f[0] == choice and set(a for a in f if a) == set(cf)), None)
            arcs = list(frame[1:]) if frame else [r for r in rels if r != choice]
        if arcs and all(a for a in arcs):
            return pred, [names(n.nodeset(a)) for a in arcs]
    # any other case frame: the relations name the predicate
    return "|".join(rels), [names(ns) for _r, ns in down]


def facts(net: Any, context: Any = None, asserted_only: bool = False,
          simple_only: bool = True) -> list[dict]:
    """Atomic propositions as facts ``{"node", "predicate", "args",
    "asserted"}``, in creation order.

    The predicate and argument order come from the SNePSLOG representation
    (``r``/``a1``... in mode 1, ``rel``/``rel-arg#`` in mode 2, the defined
    case frames in mode 3); other case frames give the predicate
    ``"rel1|rel2|..."`` with the arguments in relation order.  Rules and other
    compound propositions are skipped.  With SIMPLE_ONLY (the default) only
    facts whose every argument is a single node are kept and ``args`` is a
    list of names; otherwise ``args`` holds a list of names per position."""
    ct = resolve_context(net, context)
    out = []
    for n in select_nodes(net, include_patterns=False, include_variables=False):
        if not n.is_mol:
            continue
        asserted = bool(ct is not None and net.isassert(n, ct))
        if asserted_only and not asserted:
            continue
        f = _fact(net, n)
        if f is None:
            continue
        pred, args = f
        if simple_only:
            if not all(len(a) == 1 for a in args):
                continue
            args = [a[0] for a in args]
        out.append({"node": n.name, "predicate": pred, "args": args, "asserted": asserted})
    return out


def fact_triples(net: Any, context: Any = None, asserted_only: bool = True) -> list[Triple]:
    """The binary facts (see :func:`facts`) as ``(arg1, predicate, arg2)``
    knowledge-graph triples; by default only the asserted ones."""
    return [(f["args"][0], f["predicate"], f["args"][1])
            for f in facts(net, context, asserted_only, simple_only=True) if len(f["args"]) == 2]


# -- link prediction -------------------------------------------------------------

@dataclass
class Split:
    """Train/validation/test triples."""

    train: list[Triple]
    valid: list[Triple]
    test: list[Triple]

    def __iter__(self) -> Iterator[list[Triple]]:
        return iter((self.train, self.valid, self.test))


def split_triples(triples: Iterable[Sequence[str]], ratios: Sequence[float] = (0.8, 0.1, 0.1),
                  seed: int = 0, ensure_coverage: bool = True) -> Split:
    """Shuffle TRIPLES (duplicates removed) with SEED and cut them by RATIOS.

    With ENSURE_COVERAGE, validation and test triples whose head, relation or
    tail never occurs in the training triples are moved to training, as
    embedding models can only score entities and relations they have seen."""
    items = list(dict.fromkeys(tuple(t) for t in triples))
    if len(ratios) != 3 or any(r < 0 for r in ratios) or sum(ratios) <= 0:
        raise ValueError("ratios must be three non-negative numbers")
    random.Random(seed).shuffle(items)
    total = sum(ratios)
    n_train = int(round(len(items) * ratios[0] / total))
    n_valid = int(round(len(items) * ratios[1] / total))
    train = items[:n_train]
    valid = items[n_train:n_train + n_valid]
    test = items[n_train + n_valid:]
    if ensure_coverage:
        ents = {e for h, _r, t in train for e in (h, t)}
        rels = {r for _h, r, _t in train}
        moved = True
        while moved:
            moved = False
            for part in (valid, test):
                keep = []
                for t in part:
                    if t[0] in ents and t[2] in ents and t[1] in rels:
                        keep.append(t)
                    else:
                        train.append(t)
                        ents.update((t[0], t[2]))
                        rels.add(t[1])
                        moved = True
                part[:] = keep
    return Split(train, valid, test)


def negative_triples(triples: Iterable[Sequence[str]], entities: Optional[Sequence[str]] = None,
                     num: int = 1, seed: int = 0, corrupt: str = "both",
                     known: Optional[Iterable[Sequence[str]]] = None) -> list[Triple]:
    """NUM corrupted copies of each triple, replacing its head or tail
    (CORRUPT is ``"head"``, ``"tail"`` or ``"both"``) by an entity drawn with
    SEED, never producing a triple of TRIPLES or KNOWN (filtered setting)."""
    if corrupt not in ("head", "tail", "both"):
        raise ValueError("corrupt must be 'head', 'tail' or 'both'")
    pos = [tuple(t) for t in triples]
    ents = list(entities) if entities is not None else list(
        dict.fromkeys(e for h, _r, t in pos for e in (h, t)))
    seen = set(pos) | {tuple(t) for t in known or ()}
    rng = random.Random(seed)
    out: list[Triple] = []
    if len(ents) < 2:
        return out
    for h, r, t in pos:
        made = 0
        for _attempt in range(20 * num):
            if made == num:
                break
            side = corrupt if corrupt != "both" else rng.choice(("head", "tail"))
            e = rng.choice(ents)
            cand = (e, r, t) if side == "head" else (h, r, e)
            if cand in seen:
                continue
            seen.add(cand)
            out.append(cand)
            made += 1
    return out


# -- files ---------------------------------------------------------------------

def write_jsonl(records: Iterable[Any], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_jsonl(path: str) -> list[Any]:
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def write_csv(rows: Iterable[dict], path: str, fieldnames: Optional[Sequence[str]] = None) -> None:
    """Write dict ROWS as CSV; list and dict values are stored as JSON."""
    rows = list(rows)
    if fieldnames is None:
        fieldnames = list(dict.fromkeys(k for row in rows for k in row))
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict))
                        else v for k, v in row.items()})


def write_triples(triples: Iterable[Sequence[str]], path: str, sep: str = "\t") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for t in triples:
            fh.write(sep.join(t) + "\n")


def read_triples(path: str, sep: str = "\t") -> list[Triple]:
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if line:
                h, r, t = line.split(sep)
                out.append((h, r, t))
    return out


def export_dataset(net: Any, directory: str, context: Any = None, kind: str = "arcs",
                   ratios: Sequence[float] = (0.8, 0.1, 0.1), seed: int = 0,
                   converse: bool = False, asserted_only: bool = False,
                   text: bool = True) -> dict[str, str]:
    """Write a link-prediction dataset for NET into DIRECTORY.

    KIND ``"arcs"`` uses the arc triples of the network (:func:`triples`),
    ``"facts"`` the binary fact triples (:func:`fact_triples`).  Writes
    ``triples.tsv`` and its ``train``/``valid``/``test`` split, ``entities.txt``
    and ``relations.txt`` (one name per line, in id order),
    ``propositions.jsonl`` and ``metadata.json``; returns their paths."""
    if kind == "arcs":
        data = arc_triples(net, context, converse=converse, asserted_only=asserted_only)
    elif kind == "facts":
        data = fact_triples(net, context, asserted_only=asserted_only)
    else:
        raise ValueError("kind must be 'arcs' or 'facts'")
    os.makedirs(directory, exist_ok=True)
    split = split_triples(data, ratios, seed)
    vocab = Vocabulary.from_triples(data)
    paths = {name: os.path.join(directory, name) for name in (
        "triples.tsv", "train.tsv", "valid.tsv", "test.tsv", "entities.txt", "relations.txt",
        "propositions.jsonl", "metadata.json")}
    write_triples(data, paths["triples.tsv"])
    write_triples(split.train, paths["train.tsv"])
    write_triples(split.valid, paths["valid.tsv"])
    write_triples(split.test, paths["test.tsv"])
    for key, names in (("entities.txt", vocab.entities), ("relations.txt", vocab.relations)):
        with open(paths[key], "w", encoding="utf-8") as fh:
            fh.write("".join(name + "\n" for name in names))
    write_jsonl(propositions(net, context, text=text), paths["propositions.jsonl"])
    meta = {
        "format": "pysneps-dataset", "version": 1, "kind": kind,
        "context": context_label(net, context), "seed": seed, "ratios": list(ratios),
        "converse": converse, "asserted_only": asserted_only,
        "counts": {"triples": len(data), "train": len(split.train), "valid": len(split.valid),
                   "test": len(split.test), "entities": vocab.num_entities,
                   "relations": vocab.num_relations},
    }
    with open(paths["metadata.json"], "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    return paths
