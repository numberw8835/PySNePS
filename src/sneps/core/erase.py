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
"""Erasing nodes and resetting the network (``sneps/fns/erase``)."""

from __future__ import annotations

from typing import Any, Iterable

from .node import Node
from .nodeset import cts_compl, ctcs_get, ctcs_insert, ns_compl, ns_remove

RESET_VARIABLES = ["variables", "relations", "nodes", "command", "lastcommand",
                   "errorcommand", "contexts", "lastvalue", "assertions", "patterns",
                   "defaultct"]


def is_ns(v: Any) -> bool:
    return v is None or (isinstance(v, (tuple, list)) and (not v or isinstance(v[0], Node)))


class EraseMixin:
    _erased_ns: Any = None

    def is_isolated(self, n: Node) -> bool:
        return not any(r in self.up_relations for r in n.fcableset)

    def pointed_to(self, node: Node) -> bool:
        for var in self.value_sv("variables") or ():
            if var in ("nodes", "patterns"):
                continue
            val = self.value_sv(var)
            if isinstance(val, Node):
                if val is node:
                    return True
            elif isinstance(val, (tuple, list)) and is_ns(val):
                if any(x is node for x in val):
                    return True
        return False

    def garbage_node(self, n: Node) -> bool:
        return (self.is_isolated(n) and not self.pointed_to(n)
                and not (n.activation or n.asupport or n.jsupport or n.contexts))

    def gc_nodes(self) -> None:
        with self.let(_erased_ns=[]):
            for n in self.all_nodes():
                if self.garbage_node(n):
                    self.erase_node(n, silent=True)
            if self._erased_ns:
                self.set_sv("variables", self.clean_svars(self.value_sv("variables"),
                                                          self._erased_ns))

    def erase(self, nodes: Iterable[Node], silent: bool = False) -> None:
        """The SNePSUL ``erase`` (or ``silent-erase``) command."""
        with self.let(_erased_ns=[]):
            for n in list(nodes):
                self.erase_node(n, silent=silent)
            if self._erased_ns or silent:
                self.set_sv("variables", self.clean_svars(self.value_sv("variables"),
                                                          self._erased_ns))

    def erase_node(self, n: Any, silent: bool = False) -> None:
        with self.let(crntct=self.buildcontext(()), _erase_silent=silent):
            if not isinstance(n, Node):
                if not silent:
                    self.fresh_line()
                    self.write(f"Node {n} not found or already erased. \n")
            elif self.is_isolated(n):
                if self.sv_contains("assertions", n):
                    self.erase_contexts(n)
                    self.sv_remove("assertions", n)
                if not (silent or n.is_base or n.is_var):
                    self.fresh_line()
                    self.write("\n")
                    self.print_description(n)
                self.dismantle_node(n)
            elif not silent:
                self.fresh_line()
                self.write(f"\nNode {n} not isolated. Can't be erased. \n")

    _erase_silent = False

    def print_description(self, n: Node) -> None:
        from .printing import flat_text
        self.write(flat_text([n] + fcs_to_list(n.fcableset)) + "\n")

    def _erase_cable(self, o_n: Node, rel: str, ns: tuple) -> None:
        crel = self.converse(rel)
        for g in ns:
            self.setnodeset(g, crel, ns_remove(o_n, g.nodeset(crel)))
            if self.garbage_node(g):
                self._erase_node_1(g)

    def _erase_node_1(self, n: Node) -> None:
        silent = self._erase_silent
        if n.asupport:
            if not silent:
                self.fresh_line()
                self.write(f"\nNode {n}, a supported node, is left intact. \n")
        else:
            if not (silent or n.is_base or n.is_var):
                self.fresh_line()
                self.write("\n")
                self.print_description(n)
            self.dismantle_node(n)

    def dismantle_node(self, n: Node) -> None:
        if not (self._erase_silent or n.is_base or n.is_var):
            self.write("node dismantled. \n")
        self.sv_remove("nodes", n)
        if n.is_var:
            self.sv_remove("varnodes", n)
        elif n.is_pat:
            self.sv_remove("patterns", n)
        self._erased_ns.append(n)
        if self.nodes_by_name.get(n.name) is n:
            del self.nodes_by_name[n.name]
        for r, ns in list(n.fcableset.items()):
            self._erase_cable(n, r, ns)

    def clean_svars(self, svars: Any, erased: list) -> list:
        out: list = []
        for sv in list(svars or ()):
            val = self.value_sv(sv)
            if is_ns(val) and sv != "variables":
                new = ns_compl(tuple(val or ()), tuple(erased))
                self.set_sv(sv, new)
                if not new and not self.issys_sv(sv):
                    self.remove_sv(sv)
                    continue
            if sv not in out:
                out.append(sv)
        return out

    def erase_contexts(self, nd: Node) -> None:
        ct_set = nd.contexts
        nodes_without_support = self._remove_contexts_from_supports(self.all_nodes(), ct_set)
        for one in ct_set:
            new_ct = self.buildcontext(ns_remove(nd, one.hyps))
            for name in one.names:
                self.name_ct(new_ct, name)
            self.contexts.pop(one.hyps, None)
        for one in ns_remove(nd, nodes_without_support):
            if self.is_isolated(one):
                if not (one.is_base or one.is_var):
                    self.fresh_line()
                    self.write("\n")
                    self.print_description(one)
                self.dismantle_node(one)
                self._erased_ns.append(one)

    def _remove_contexts_from_supports(self, allnodes: Iterable[Node], ct_set: tuple) -> tuple:
        from .nodeset import ns_insert
        without: tuple = ()
        for one in allnodes:
            supp = one.asupport
            if supp:
                new = filter_support(supp, ct_set)
                one.asupport = new
                if not new:
                    without = ns_insert(one, without)
        return without

    def resetnet(self, reset_relations: bool = False) -> None:
        """Remove all nodes and contexts (and, optionally, relations)."""
        self.clear_infer_all()
        for n in self.all_nodes():
            n.net = None
        self.nodes_by_name.clear()
        self.nogoods = []
        self.oknogoods = []
        self.node_counter = 0
        for p in self.id_counters:
            self.id_counters[p] = 0
        self.context_counter = 0
        self.reset_attachments()
        keep = {k: self.svars[k] for k in ("relations",) if k in self.svars}
        self.svars.clear()
        self._index.clear()
        self.svars.update(keep)
        if reset_relations:
            for r in list(self.value_sv("relations") or ()):
                if self.pathdefs.get(r):
                    self.undefine_path([r])
                self.undefine_r(r)
            self.svars.pop("relations", None)
            self.converses.clear()
            self.down_relations.clear()
            self.up_relations.clear()
            self.pathdefs.clear()
            self.altrels.clear()
            self.fwd_paths.clear()
            for r in self.initial_relations():
                self.new_r(r)
        self._sv_store("nodes", ())
        self._sv_store("varnodes", ())
        self._sv_store("assertions", ())
        self._sv_store("patterns", ())
        self.svars["variables"] = list(RESET_VARIABLES)
        self.contexts.clear()
        self.svars["contexts"] = self.contexts
        self.name_ct(self.buildcontext(()), "default-defaultct")
        self.set_sv("defaultct", "default-defaultct")
        self.crntct = "default-defaultct"
        self.fresh_line()
        self.write("\nNet reset" + ("" if reset_relations else
                                    " - Relations and paths are still defined"))

    def initial_relations(self) -> tuple:
        from .network import INITIAL_RELATIONS
        return INITIAL_RELATIONS

    def clear_infer_all(self) -> None:
        for n in self.all_nodes():
            n.activation = None

    def reset_attachments(self) -> None:
        """Hook: forget attached functions and primitive actions (SNIP)."""


def filter_support(supp: tuple, ct_set: tuple) -> tuple:
    new: tuple = ()
    for ot in ("hyp", "der", "ext"):
        for c in cts_compl(ctcs_get(ot, supp), ct_set):
            new = ctcs_insert(ot, c, new)
    return new


def fcs_to_list(fcs: dict) -> list:
    out: list = []
    for r, ns in fcs.items():
        out.append(r)
        out.append(list(ns))
    return out
