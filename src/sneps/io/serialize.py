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
"""Saving and restoring networks as JSON (``outnet``/``innet``).

The JSON document records relations, path definitions, nodes with their
descending cables, contexts, assertion supports, nogoods and SNePS
variables, so that a network can be restored exactly (node names and
creation order included).  :func:`to_dict`/:func:`from_dict` give the same
data as Python objects.
"""

from __future__ import annotations

import json
from typing import Any

from ..core.context import Context
from ..core.node import Node
from ..core.nodeset import ns_make

FORMAT = "pysneps-network"
VERSION = 1


def _enc(net: Any, v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        return {"str": v}
    if isinstance(v, Node):
        return {"node": v.name}
    if isinstance(v, Context):
        return {"context": v.order}
    if isinstance(v, (list, tuple)):
        if v and all(isinstance(x, Node) for x in v):
            return {"nodes": [x.name for x in v]}
        return {"list": [_enc(net, x) for x in v]}
    return {"repr": repr(v)}


def _dec(v: Any, nodes: dict, contexts: dict) -> Any:
    if not isinstance(v, dict):
        return v
    if "str" in v:
        return v["str"]
    if "node" in v:
        return nodes.get(v["node"])
    if "nodes" in v:
        return ns_make(nodes[x] for x in v["nodes"] if x in nodes)
    if "context" in v:
        return contexts.get(v["context"])
    if "sym" in v:                      # names, in files of earlier versions
        return v["sym"]
    if "list" in v:
        return [_dec(x, nodes, contexts) for x in v["list"]]
    return None


def to_dict(net: Any) -> dict:
    """A JSON-compatible description of the whole network."""
    nodes = sorted(net.all_nodes(), key=lambda n: n.order)
    out_nodes = []
    for n in nodes:
        out_nodes.append({
            "name": n.name,
            "type": n.type,
            "order": n.order,
            "cables": {r: [m.name for m in ns] for r, ns in net.down_fcs(n)},
            "freevars": [v.name for v in n.freevars],
            "support": [[ot, [c.order for c in cts]] for ot, cts in n.asupport],
            "snepslog": n.snepslog if isinstance(n.snepslog, str) else (
                getattr(n.snepslog, "name", None) if n.snepslog is not None else None),
        })
    contexts = [{"order": c.order, "hyps": [h.name for h in c.hyps], "names": list(c.names),
                 "kinconsistent": c.kinconsistent, "okinconsistent": c.okinconsistent}
                for c in sorted(net.contexts.values(), key=lambda c: c.order)]
    rels = [r for r in reversed(net.value_sv("relations") or []) if net.isdn_r(r)]
    svars = {}
    for name in net.value_sv("variables") or []:
        if name in ("nodes", "contexts", "relations", "variables", "assertions", "patterns",
                    "varnodes"):
            continue
        val = net.value_sv(name)
        if isinstance(val, Context):
            continue
        svars[name] = _enc(net, val)
    return {
        "format": FORMAT,
        "version": VERSION,
        "counters": {"node": net.node_counter, "ids": dict(net.id_counters),
                     "context": net.context_counter},
        "relations": rels,
        "paths": {r: p for r, p in net.pathdefs.items()},
        "nodes": out_nodes,
        "contexts": contexts,
        "assertions": [n.name for n in net.value_sv("assertions") or ()],
        "nogoods": [[h.name for h in ng] for ng in net.nogoods],
        "oknogoods": [[h.name for h in ng] for ng in net.oknogoods],
        "variables": list(net.value_sv("variables") or []),
        "svars": svars,
        "defaultct": net.value_sv("defaultct"),
    }


def from_dict(net: Any, data: dict) -> Any:
    """Replace the contents of NET by the network described by DATA."""
    if data.get("format") != FORMAT:
        raise ValueError("not a PySNePS network document")
    from ..io.streams import NullOutputStream
    with net.let(outunit=NullOutputStream()):
        net.resetnet(True)
    for r in data["relations"]:
        if not net.is_r(r):
            net.new_r(r)
    nodes: dict[str, Node] = {}
    for nd in data["nodes"]:
        n = net.newnode(nd["name"], nd["type"], nd["order"])
        nodes[n.name] = n
        if nd.get("snepslog") is not None:
            n.snepslog = nd["snepslog"]
    for nd in data["nodes"]:
        n = nodes[nd["name"]]
        cs = [(r, ns_make(nodes[m] for m in ms)) for r, ms in nd["cables"].items()]
        if cs:
            n.fcableset = net.make_fcs(cs)
            net.attachnode(n, cs)
        n.freevars = ns_make(nodes[v] for v in nd.get("freevars", ()))
        if n.is_var:
            net.sv_add("varnodes", n)
        elif n.is_pat:
            net.sv_add("patterns", n)
    for n in sorted(nodes.values(), key=lambda n: n.order):
        n.height = net.calcheight(n) if net.down_fcs(n) else 0
    net.contexts.clear()
    contexts: dict[int, Context] = {}
    for cd in data["contexts"]:
        ct = net.newcontext(cd["order"], ns_make(nodes[h] for h in cd["hyps"]))
        ct.kinconsistent = cd["kinconsistent"]
        ct.okinconsistent = cd["okinconsistent"]
        contexts[ct.order] = ct
        for name in reversed(cd["names"]):
            net.name_ct(ct, name)
    for nd in data["nodes"]:
        n = nodes[nd["name"]]
        n.asupport = tuple((ot, tuple(sorted((contexts[o] for o in cts), key=lambda c: -c.order)))
                           for ot, cts in nd.get("support", ()))
    for name in data.get("assertions", ()):
        net.sv_add("assertions", nodes[name])
    net.nogoods = [ns_make(nodes[h] for h in ng) for ng in data.get("nogoods", ())]
    net.oknogoods = [ns_make(nodes[h] for h in ng) for ng in data.get("oknogoods", ())]
    for rel, path in data.get("paths", {}).items():
        net.pathdefs[rel] = path
        net.altrels[rel] = net.pathfirstrels(path)
        for triple in net.pathconnect(path):
            net.fwd_paths.setdefault(triple[0], []).insert(0, [rel] + list(triple[1:]))
    for name, val in data.get("svars", {}).items():
        net.set_sv(name, _dec(val, nodes, contexts))
    counters = data["counters"]
    net.node_counter = counters["node"]
    net.id_counters.update(counters["ids"])
    net.context_counter = counters["context"]
    if data.get("defaultct"):
        net.set_sv("defaultct", data["defaultct"])
        net.crntct = data["defaultct"]
    return net


def save(net: Any, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(to_dict(net), fh, indent=1)


def load_into(net: Any, path: str) -> Any:
    with open(path, encoding="utf-8") as fh:
        return from_dict(net, json.load(fh))


def load(path: str) -> Any:
    from ..network import Network
    return load_into(Network(), path)
