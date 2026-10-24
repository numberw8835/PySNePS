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
"""Describing nodes and contexts (``sneps/fns/dd``, ``hyp``)."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .printing import flat_text, pretty_text
from .context import Context
from .network import SNePSError
from .node import Node
from .nodeset import ns_compl, ns_insert, ns_issubset, ns_ismemb, ns_make
from .erase import fcs_to_list


class DescribeMixin:
    # ------------------------------------------------------------------
    # node trees
    def des1(self, n: Node, described: list, full: bool = False) -> list:
        """DES1: the description tree of N; DESCRIBED is a one-element list
        holding the node set of nodes already described."""
        tree: list = [n]
        if ns_ismemb(n, described[0]):
            return tree
        described[0] = ns_insert(n, described[0])
        for r, ns in self.n_to_cs(n):
            if r in self.up_relations:
                continue
            cable: list = [r]
            for n1 in ns:
                if n1.is_base or n1.is_var:
                    described[0] = ns_insert(n1, described[0])
                    cable.append(n1)
                else:
                    cable.append(self.des1(n1, described, full))
            tree.append(cable)
        if full:
            tree.extend(self.descrcontext_cable_set(n.asupport))
        return tree

    def pp_nodetree(self, tree: Any) -> None:
        self.fresh_line()
        self.write(pretty_text(tree, escape=False, column=self.outunit.column))
        self.write("\n")

    def describe_nodes(self, ns: Iterable[Node], full: bool = False) -> None:
        ns = list(ns)
        described: list = [()]
        if ns:
            self.write("\n")
            for n in ns:
                if not ns_ismemb(n, described[0]):
                    self.pp_nodetree(self.des1(n, described, full))

    def dump_nodes(self, ns: Iterable[Node]) -> None:
        ns = list(ns)
        if ns:
            self.write("\n")
            for n in ns:
                self.write(flat_text([n, fcs_to_list(n.fcableset)]))
                self.write("\n")

    def descrcontext(self, ct: Context) -> list:
        return [["assertions", [self.slight_describe_or_surface(h) for h in ct.hyps]],
                ["named", list(ct.names)],
                ["kinconsistent", self.isinconsis_ct(ct)]]

    def slight_describe_or_surface(self, n: Node, stream: Any = None) -> Any:
        """Overridden by SNePSLOG to show wffs; here the node itself."""
        return n

    def descrcontext_cable_set(self, ctcs: tuple) -> list:
        out = []
        for ot, cts in ctcs:
            for c in cts:
                out.append([ot, self.descrcontext(c)])
        return out

    # ------------------------------------------------------------------
    # context commands (hyp)
    def legalcontext(self, ns: tuple) -> tuple:
        if ns_issubset(ns, self.value_sv("assertions") or ()):
            return ns
        raise SNePSError(f"One or more nodes are not assertions {flat_text(list(ns))}",
                         "context", "legalcontext")

    def crntcontext(self, ctdescr: Optional[list]) -> Any:
        """The context name designated by a ``:context`` description.

        CTDESCR is ``None`` (the default context), ``["all-hyps"]``,
        ``[name]`` or ``[nodes, name]`` (with NODES already a node set).
        """
        if not ctdescr:
            return self.value_sv("defaultct")
        first = ctdescr[0]
        if first == "all-hyps":
            self.set_sv("%%globalcontext%%",
                        self.fullbuildcontext(self.legalcontext(self.value_sv("assertions") or ())))
            return "%%globalcontext%%"
        if isinstance(first, str) and len(ctdescr) == 1:
            if not isinstance(self.value_sv(first), Context):
                self.name_ct(self.fullbuildcontext(()), first)
            return first
        if len(ctdescr) == 2 and isinstance(ctdescr[1], str):
            self.name_ct(self.fullbuildcontext(self.legalcontext(tuple(first))), ctdescr[1])
            return ctdescr[1]
        raise SNePSError(f"Error in context description {ctdescr}", "context", "crntcontext")

    def describe_context(self, cname: Any = None) -> None:
        if cname is None:
            cname = self.value_sv("defaultct")
        ct = self.get_context(cname)
        if ct is None:
            raise SNePSError(f"the following context is invalid: {cname}",
                             "contexts", "describe-context")
        with self.let(crntct=cname):
            self.write("\n" + flat_text(self.descrcontext(ct)) + "\n")

    def _check_hyps(self, hyps: tuple, cmd: str) -> None:
        assertions = self.value_sv("assertions") or ()
        if not ns_issubset(hyps, assertions):
            raise SNePSError("the following nodes are not hypotheses: "
                             + flat_text(list(ns_compl(hyps, assertions))), "context", cmd)

    def set_context(self, hyps: Iterable[Node], cname: Any = None) -> None:
        hyps = ns_make(hyps)
        ct_name = cname if cname is not None else self.value_sv("defaultct")
        self._check_hyps(hyps, "set-context")
        newct = self.fullbuildcontext(hyps)
        if not self.ck_inconsistency(newct):
            self.name_ct(newct, ct_name)
            self.describe_context(ct_name)

    def add_to_context(self, hyps: Iterable[Node], cname: Any = None) -> None:
        hyps = ns_make(hyps)
        ct_name = cname if cname is not None else self.value_sv("defaultct")
        old = self.get_context(ct_name)
        if old is None:
            raise SNePSError(f"the value of {ct_name} is not a context", "context", "add-to-context")
        self._check_hyps(hyps, "add-to-context")
        newct = self.fullbuildcontext(hyps, (old,))
        if not self.ck_inconsistency(newct):
            self.name_ct(newct, ct_name)
            self.describe_context(ct_name)

    def remove_from_context(self, hyps: Iterable[Node], cname: Any = None) -> Optional[Context]:
        """Returns the new context, or None if it is inconsistent."""
        hyps = ns_make(hyps)
        ct_name = cname if cname is not None else self.value_sv("defaultct")
        old = self.get_context(ct_name)
        if old is None:
            raise SNePSError(f"the value of {ct_name} is not a context", "context",
                             "remove-from-context")
        newct = self.fullbuildcontext(ns_compl(old.hyps, hyps))
        if not self.ck_inconsistency(newct):
            return self.name_ct(newct, ct_name)
        return None

    def list_context_names(self) -> list:
        names: list = []
        for ct in sorted(self.contexts.values(), key=lambda c: -c.order):
            names = list(ct.names) + names
        self.write("\n" + flat_text(names) + "\n")
        return names

    def set_default_context(self, cname: Any) -> None:
        if not isinstance(self.value_sv(cname), Context):
            raise SNePSError(f"the following context is invalid: {cname}",
                             "context", "set-default-context")
        self.set_sv("defaultct", cname)
        self.crntct = cname
        self.describe_context(cname)

    def describe_all_contexts(self) -> None:
        for ct in self.allct():
            self.write(f"\n\n  CONTEXT-NAMES: {flat_text(list(ct.names))}"
                       f"\n  CONTEXT-HYPS: {flat_text(list(ct.hyps))}")

    def ck_inconsistency(self, ct: Context) -> bool:
        """Hook for SNeBR: True if CT is inconsistent and the change is refused."""
        return False

    # ------------------------------------------------------------------
    # graph drawing (the ``show`` command writes GraphViz DOT)
    def to_dot(self, ns: Iterable[Node]) -> str:
        lines = ["digraph RE { "]
        described: list = [()]

        def gen(tree: list) -> Node:
            m = tree[0]
            if len(tree) == 1:
                lines.append(f'"{self.node_label(m)}"; ')
            for cable in tree[1:]:
                for node in cable[1:]:
                    target = node if not isinstance(node, list) else gen(node)
                    lines.append(f'"{self.node_label(m)}" -> "{self.node_label(target)}" '
                                 f'[label="{cable[0]}"]; ')
            return m
        for n in ns:
            if not ns_ismemb(n, described[0]):
                gen(self.des1(n, described))
        lines.append("} ")
        return "\n".join(lines) + "\n"

    def node_label(self, n: Node) -> str:
        return str(n)
