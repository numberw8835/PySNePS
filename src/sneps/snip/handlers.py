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
"""SNIP rule handlers (``snip/fns/or-ent`` ... ``whenever-do``).

Each handler receives a report from an antecedent (or a request) together
with the rule-use channel it arrived on, updates the rule-use information
(RUIs) and sends conclusions to the consequent when the rule fires.
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.network import SNePSError
from ..core.node import Node
from ..core.nodeset import ctcs_insert, cts_make, ns_insert
from ..match.unify import restrict_binding_to_pat
from ..util.lists import union as ordered_union
from .multi import INTEND, Frame
from .structs import (FALSE, NEG, POS, REQUESTED, TRUE, UNKNOWN, RUI, Cell, Cqch, Report,
                      alist_assoc, alist_rassoc_list, change_tag_support, combine_ots,
                      combine_ots_star, combinations_of, cqchset_update, fns_flag, fns_support,
                      fns_to_suplist, fns_update, nodeset_to_fnodeset, request_all,
                      rui_compatible, rui_select, rui_update, ruis_update, sbst_eq,
                      sbst_is_compatible, sbst_issubset, sbst_restrict, sbst_set_member,
                      sbst_union, sup_merge)


def _sub_equal(a: Any, b: Any) -> bool:
    a, b = tuple(a or ()), tuple(b or ())
    return len(a) == len(b) and all(x[0] is y[0] and x[1] is y[1] for x, y in zip(a, b))


def _assoc_value(key: Any, al: list) -> list:
    cell = alist_assoc(key, al)
    return list(cell[1]) if cell is not None else []


class RuleHandlersMixin:
    # ------------------------------------------------------------------
    # rule-use information
    def get_rule_use_info(self, f: Frame, report: Report, cqch: Cqch) -> list:
        sbst, ant, supp = report.subst, report.signature, report.support
        ants = cqch.ants
        updated = list(cqch.ruiset or [])
        result: list = []
        for rui in list(cqch.ruiset or []):
            flag = fns_flag(ant, rui.fns)
            if sbst_is_compatible(sbst, rui.subst):
                if not rui.fns or flag in (UNKNOWN, REQUESTED):
                    result = ruis_update(rui_update(RUI(sbst_union(rui.subst, sbst), rui.poscount,
                                                        rui.negcount, rui.fns, rui.remarkedp),
                                                    ant, supp, report.sign), result)
                elif flag in (TRUE, FALSE) and self.filter_sup(fns_support(ant, rui.fns),
                                                               report.context):
                    result = ruis_update(RUI(rui.subst, rui.poscount, rui.negcount,
                                             fns_update(rui.fns, ant, supp, flag), rui.remarkedp),
                                         result)
        for rui in result:
            updated = ruis_update(rui, updated)
            f.RULE_USE_CHANNELS = cqchset_update(Cqch(cqch.channel, ants, updated),
                                                 f.RULE_USE_CHANNELS)
        return result

    def get_rule_use_info_sindexing(self, f: Frame, report: Report, cqch: Cqch) -> Optional[list]:
        ant, sbst, sign, supp = report.signature, report.subst, report.sign, report.support
        ch, ants = cqch.channel, cqch.ants
        sindex_ruiset = list(cqch.ruiset or [])
        sindex = [p[1] for p in sbst_restrict(sbst, self.all_vars(f.NODE))]
        cell = alist_assoc(sindex, sindex_ruiset)
        ruis = list(cell[1]) if cell is not None else []
        result = None
        if not ruis:
            ruis = request_all([RUI(ch.filter, 0, 0, nodeset_to_fnodeset(ants), False)])
            cell = Cell([sindex, ruis])
            sindex_ruiset = [cell] + sindex_ruiset
        rui = ruis[0]
        flag = fns_flag(ant, rui.fns)
        if not rui.fns or flag in (UNKNOWN, REQUESTED):
            ruis = [rui_update(RUI(sbst_union(rui.subst, sbst), rui.poscount, rui.negcount,
                                   rui.fns, rui.remarkedp), ant, supp, sign)]
            alist_assoc(sindex, sindex_ruiset)[1] = ruis
            result = ruis
        elif flag in (TRUE, FALSE) and self.filter_sup(fns_support(ant, rui.fns), report.context):
            ruis = [RUI(rui.subst, rui.poscount, rui.negcount,
                        fns_update(rui.fns, ant, supp, flag), rui.remarkedp)]
            alist_assoc(sindex, sindex_ruiset)[1] = ruis
            result = None
        f.RULE_USE_CHANNELS = cqchset_update(Cqch(ch, ants, sindex_ruiset), f.RULE_USE_CHANNELS)
        return result

    def get_rule_use_info_ptree(self, f: Frame, report: Report, cqch: Cqch) -> list:
        ch, ants = cqch.channel, cqch.ants
        ptree, adj, pnode_ruiset = cqch.ruiset
        pnode_ruiset = list(pnode_ruiset)
        sign, ant = report.sign, report.signature
        if any(a is ant for a in ants) or not ants:
            updated = [RUI(report.subst, 1 if sign == POS else 0, 1 if sign == NEG else 0,
                           fns_update(nodeset_to_fnodeset((ant,)), ant, report.support,
                                      TRUE if sign == POS else FALSE), False)]
        else:
            updated = []
        result = list(updated)
        cur = ant
        while updated:
            parent = None
            for pair in adj:
                if pair[0] == cur:
                    parent = pair
                    break
            if parent is None:
                parent = alist_rassoc_list(cur, adj)
            if parent is None:
                adj_node = None
            else:
                adj_node = parent[1] if cur == parent[0] else parent[0]
            cell = alist_assoc(cur, pnode_ruiset)
            if cell is None:
                pnode_ruiset = [Cell([cur, list(updated)])] + pnode_ruiset
            else:
                new = list(cell[1])
                for rui in updated:
                    new = ruis_update(rui, new)
                cell[1] = new
            updated = _get_compatible_ruis(updated, _assoc_value(adj_node, pnode_ruiset)
                                           if adj_node is not None else [])
            updated = _get_new_ruis(updated, _assoc_value(parent, pnode_ruiset)
                                    if parent is not None else [])
            result = result + updated
            cur = parent
        f.RULE_USE_CHANNELS = cqchset_update(Cqch(ch, ants, [ptree, adj, pnode_ruiset]),
                                             f.RULE_USE_CHANNELS)
        return result

    def _ruis_for(self, f: Frame, report: Report, cqch: Cqch, allow_empty: bool = False) -> list:
        ants = cqch.ants
        if (allow_empty and not ants) or self.is_all_pat_same_vars(ants):
            return self.get_rule_use_info_sindexing(f, report, cqch) or []
        return self.get_rule_use_info(f, report, cqch)

    # ------------------------------------------------------------------
    # supports of conclusions
    def _known_instance_supports(self, f: Frame, ct: Any, subst: Any, fn: Any) -> tuple:
        node = f.NODE
        new: tuple = ()
        freevars = node.get_freevars()
        for inst in list(f.KNOWN_INSTANCES or ()):
            instnode = self.applysubst(node, inst.subst)
            supinst = self.filter_sup(instnode.asupport, ct)
            if supinst and sbst_issubset(sbst_restrict(subst, freevars),
                                         sbst_restrict(inst.subst, freevars)):
                new = sup_merge(new, fn(supinst))
        return new

    def _pairwise_support(self, sup1: tuple, sup2: tuple) -> tuple:
        """COMPUTE-NEW-SUPPORT1.AND / .NOR / .V-ENT: every context of SUP2
        combined with every context of SUP1."""
        new: tuple = ()
        for ot1, cts1 in sup2 or ():
            for ct1 in cts1:
                for ot2, cts2 in sup1 or ():
                    for ct2 in cts2:
                        new = ctcs_insert(combine_ots(ot1, ot2),
                                          self.fullbuildcontext((), cts_make((ct1, ct2))), new)
        return new

    def _combination_support(self, fns: Any, sup: tuple) -> tuple:
        """COMPUTE-NEW-SUPPORT1.&-ENT / .AND-OR / .NUM-QUANT"""
        new: tuple = ()
        combos = combinations_of(sup, fns_to_suplist(fns))
        for i in range(0, len(combos), 2):
            new = ctcs_insert(combine_ots_star(combos[i]),
                              self.fullbuildcontext((), combos[i + 1]), new)
        return new

    def _support_v_ent(self, f: Frame, ch: Any, rui: RUI, ant_report: Report) -> tuple:
        node = f.NODE
        with self.let(crntct=ch.context):
            new: tuple = ()
            sig = ant_report.signature
            if self.isassert(node):
                new = self._pairwise_support(node.asupport, fns_support(sig, rui.fns))
            return sup_merge(new, self._known_instance_supports(
                f, ch.context, rui.subst,
                lambda s: self._pairwise_support(s, fns_support(sig, rui.fns)))) \
                if f.KNOWN_INSTANCES else new

    def _support_combination(self, f: Frame, ch: Any, fns: Any, subst: Any) -> tuple:
        node = f.NODE
        with self.let(crntct=ch.context):
            new: tuple = ()
            if self.isassert(node):
                new = self._combination_support(fns, node.asupport)
            if f.KNOWN_INSTANCES:
                new = sup_merge(new, self._known_instance_supports(
                    f, ch.context, subst, lambda s: self._combination_support(fns, s)))
            return new

    # ------------------------------------------------------------------
    # handlers
    def rule_handler_v_ent(self, f: Frame, ant_report: Report, cqch: Cqch) -> bool:
        node = f.NODE
        for rui in self._ruis_for(f, ant_report, cqch):
            if ant_report.sign == POS and rui.poscount >= 1:
                restr = rui.subst
                ch = cqch.channel
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nSince", (node,), None)
                    self.remark("and", (ant_report.signature,), restr)
                    self.remark("I infer", (ch.destination,), restr)
                self.send_reports([Report(sbst_restrict(rui.subst, ch.destination.get_freevars()),
                                          self._support_v_ent(f, ch, rui, ant_report), POS,
                                          node, None, cqch.channel.context)], ch)
        return True

    def rule_handler_and_ent(self, f: Frame, ant_report: Report, cqch: Cqch) -> None:
        node = f.NODE
        ants = cqch.ants
        if self.is_all_pat_same_vars(ants):
            ruis = self.get_rule_use_info_sindexing(f, ant_report, cqch) or []
        else:
            ruis = self.get_rule_use_info_ptree(f, ant_report, cqch)
        for rui in ruis:
            if rui.poscount == len(ants):
                restr = rui.subst
                ch = cqch.channel
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nSince", (node,), restr)
                    for ant in ants:
                        self.remark("and", (ant,), restr)
                    self.remark("I infer", (ch.destination,), restr)
                self.send_reports([Report(sbst_restrict(rui.subst, ch.destination.get_freevars()),
                                          self._support_combination(f, ch, rui.fns, rui.subst),
                                          POS, node, None, ch.context)], ch)

    def rule_handler_and_or(self, f: Frame, ant_report: Report, cqch: Cqch) -> None:
        node = f.NODE
        mn = node.nodeset("min")[0].to_number()
        mx = node.nodeset("max")[0].to_number()
        tot = len(node.nodeset("arg"))
        ch = cqch.channel
        ants = cqch.ants
        for rui in self._ruis_for(f, ant_report, cqch):
            if rui.poscount > mx:
                raise SNePSError("Contradiction in an and-or: More true arguments than max in "
                                 f"node {node}", "SNIP", "report-contradiction.and-or")
            if rui.negcount > tot - mn:
                raise SNePSError("Contradiction in an and-or: More false arguments than tot-min "
                                 f"in node {node}", "SNIP", "report-contradiction.and-or")
            if rui.poscount == mx:
                restr = rui.subst
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self._inform_and_or(f, restr, ch, ants, rui, TRUE,
                                        "and", "I infer it is not the case that")
                self.send_reports([Report(restrict_binding_to_pat(rui.subst, ch.destination),
                                          self._support_combination(
                                              f, ch, rui_select(rui, (TRUE,)), rui.subst),
                                          NEG, node, None, ch.context)], ch)
            elif rui.negcount == tot - mn:
                restr = rui.subst
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self._inform_and_or(f, restr, ch, ants, rui, FALSE,
                                        "and it is not the case that", "I infer")
                self.send_reports([Report(restrict_binding_to_pat(rui.subst, ch.destination),
                                          self._support_combination(
                                              f, ch, rui_select(rui, (FALSE,)), rui.subst),
                                          POS, node, None, ch.context)], ch)

    def _inform_and_or(self, f: Frame, restr: Any, ch: Any, ants: tuple, rui: RUI, flag: str,
                       msg: str, final: str) -> None:
        self.remark("\nSince", (f.NODE,), None)
        for a in ants:
            if fns_flag(a, rui.fns) == flag:
                self.remark(msg, (a,), restr)
        self.remark(final, (ch.destination,), restr)

    def rule_handler_thresh(self, f: Frame, ant_report: Report, cqch: Cqch) -> None:
        node = f.NODE
        i = node.nodeset("thresh")[0].to_number()
        n = len(node.nodeset("arg"))
        j = node.nodeset("threshmax")[0].to_number() if node.nodeset("threshmax") else n - 1
        ants = cqch.ants
        for rui in self._ruis_for(f, ant_report, cqch):
            if rui.poscount >= i and rui.negcount > n - j - 1:
                raise SNePSError(f"Contradiction in a thresh: in node {node} number of true "
                                 "args in excluded range", "SNIP", "report-contradiction.thresh")
            if rui.poscount >= i and rui.negcount == n - j - 1:
                restr = rui.subst
                ch = cqch.channel
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self._inform_thresh(f, restr, ch, ants, rui, "I infer")
                combos = _combinations_fns(i, rui_select(rui, (TRUE,)), rui_select(rui, (FALSE,)))
                self.send_reports([Report(restrict_binding_to_pat(rui.subst, ch.destination),
                                          self._support_thresh(f, ch, combos, rui.subst),
                                          POS, node, None, ch.context)], ch)
            elif rui.poscount == i - 1 and rui.negcount >= n - j:
                restr = rui.subst
                ch = cqch.channel
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self._inform_thresh(f, restr, ch, ants, rui, "I infer it is not the case that")
                combos = _combinations_fns(n - j, rui_select(rui, (FALSE,)),
                                           rui_select(rui, (TRUE,)))
                self.send_reports([Report(restrict_binding_to_pat(rui.subst, ch.destination),
                                          self._support_thresh(f, ch, combos, rui.subst),
                                          NEG, node, None, ch.context)], ch)

    def _inform_thresh(self, f: Frame, restr: Any, ch: Any, ants: tuple, rui: RUI,
                       final: str) -> None:
        self.remark("\nSince", (f.NODE,), None)
        for a in ants:
            fl = fns_flag(a, rui.fns)
            if fl == TRUE:
                self.remark("and", (a,), restr)
            elif fl == FALSE:
                self.remark("and it is not the case that", (a,), restr)
        self.remark(final, (ch.destination,), restr)

    def _support_thresh(self, f: Frame, ch: Any, combos: list, subst: Any) -> tuple:
        node = f.NODE
        with self.let(crntct=ch.context):
            new: tuple = ()
            if self.isassert(node):
                for comb in combos:
                    new = sup_merge(new, self._combination_support(comb, node.asupport))
            if f.KNOWN_INSTANCES:
                def per(s: tuple) -> tuple:
                    out: tuple = ()
                    for comb in combos:
                        out = sup_merge(out, self._combination_support(comb, s))
                    return out
                new = sup_merge(new, self._known_instance_supports(f, ch.context, subst, per))
            return new

    def rule_handler_num_ent(self, f: Frame, ant_report: Report, cqch: Cqch) -> None:
        node = f.NODE
        thresh = node.nodeset("thresh")[0].to_number()
        for rui in self._ruis_for(f, ant_report, cqch):
            if not rui.poscount < thresh:
                restr = rui.subst
                ch = cqch.channel
                # As in SNePS 2.8, only the first remark survives the
                # successive UNLESS-REMARKEDP.RUI forms.
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nSince", (node,), restr)
                self.send_reports([Report(sbst_restrict(rui.subst, ch.destination.get_freevars()),
                                          self._support_combination(f, ch, rui.fns, rui.subst),
                                          POS, node, None, ch.context)], ch)

    def _support_and_nor(self, f: Frame, ch: Any, rui: RUI, antrep: Report, nor: bool) -> tuple:
        node = f.NODE
        with self.let(crntct=ch.context):
            if nor:
                if (self.isassert(node) and len(node.nodeset("arg")) == 1
                        and antrep.sign == POS):
                    new = antrep.support
                else:
                    new = change_tag_support(antrep.support)
            else:
                new = ()
                if self.isassert(node):
                    new = self._pairwise_support(antrep.support, node.asupport)
            if f.KNOWN_INSTANCES:
                new = sup_merge(new, self._known_instance_supports(
                    f, ch.context, rui.subst, lambda s: self._pairwise_support(antrep.support, s)))
            return new

    def rule_handler_and(self, f: Frame, ant_report: Report, cqch: Cqch) -> bool:
        node = f.NODE
        ch = cqch.channel
        for rui in self._ruis_for(f, ant_report, cqch, allow_empty=True):
            if ant_report.sign == NEG:
                if ant_report.signature is ch.destination:
                    restr = rui.subst
                    if not rui.remarkedp:
                        rui = rui._replace(remarkedp=True)
                        self.remark("\nI know it is not the case that", (ch.destination,), restr)
                    self.send_reports([Report(sbst_restrict(rui.subst, node.get_freevars()),
                                              self._support_and_nor(f, ch, rui, ant_report, False),
                                              NEG, node, None, ch.context)], ch)
            elif ant_report.sign == POS:
                if (ant_report.signature is ch.destination
                        or self.applysubst(node, ant_report.subst) is ant_report.node):
                    restr = rui.subst
                    if not rui.remarkedp:
                        rui = rui._replace(remarkedp=True)
                        self.remark("\nIt is the case that", (ch.destination,), restr)
                    self.send_reports([Report(sbst_restrict(rui.subst,
                                                            ch.destination.get_freevars()),
                                              self._support_and_nor(f, ch, rui, ant_report, False),
                                              POS, node, None, ch.context)], ch)
        return True

    def rule_handler_nor(self, f: Frame, ant_report: Report, cqch: Cqch) -> bool:
        node = f.NODE
        ch = cqch.channel
        for rui in self._ruis_for(f, ant_report, cqch, allow_empty=True):
            if ant_report.sign == POS:
                restr = rui.subst
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nI know it is not the case that", (ch.destination,), restr)
                self.send_reports([Report(sbst_restrict(rui.subst, ch.destination.get_freevars()),
                                          self._support_and_nor(f, ch, rui, ant_report, True),
                                          NEG, node, None, ch.context)], ch)
            elif ant_report.sign == NEG:
                if ant_report.signature is not ch.destination:
                    restr = rui.subst
                    if not rui.remarkedp:
                        rui = rui._replace(remarkedp=True)
                        self.remark("\nIt is the case that", (ch.destination,), restr)
                    self.send_reports([Report(sbst_restrict(rui.subst,
                                                            ch.destination.get_freevars()),
                                              self._support_and_nor(f, ch, rui, ant_report, True),
                                              POS, node, None, ch.context)], ch)
        return True

    # -- numerical quantifiers ----------------------------------------------
    def rule_handler_num_quant(self, f: Frame, ant_report: Report, cqch: Cqch) -> None:
        node = f.NODE

        def num(r: str) -> Any:
            ns = node.nodeset(r)
            return ns[0].to_number() if ns else None
        i, j, k = num("emin"), num("emax"), num("etot")
        n = len(node.nodeset("&ant"))
        type1 = i is not None and j is not None and k is not None
        type2 = i is not None and j is None and k is not None
        type3 = i is None and j is not None and k is None
        type4 = i is not None and j is not None and k is None
        ch = cqch.channel
        destn = ch.destination
        for rui in self.get_rule_use_info_ptree(f, ant_report, cqch):
            f_sbst = sbst_restrict(rui.subst, node.get_freevars())
            q_sbst = sbst_restrict(rui.subst, node.quantified_vars())
            if rui.poscount == n + 1 and rui.negcount == 0:
                f.NUM_QUANT_POS_INSTANCES = _update_instances(f_sbst, q_sbst,
                                                              f.NUM_QUANT_POS_INSTANCES)
                if ((type1 or type3 or type4)
                        and len(_select_instances(f_sbst, f.NUM_QUANT_POS_INSTANCES)) == j):
                    self._send_reports_num_quant(f, NEG, n, f_sbst, rui, cqch)
            elif rui.poscount == n and rui.negcount == 1:
                if ((ant_report.signature is destn and ant_report.sign == NEG)
                        or (ant_report.signature is not destn and ant_report.sign == POS)):
                    f.NUM_QUANT_NEG_INSTANCES = _update_instances(f_sbst, q_sbst,
                                                                  f.NUM_QUANT_NEG_INSTANCES)
                    if ((type1 or type2) and
                            len(_select_instances(f_sbst, f.NUM_QUANT_NEG_INSTANCES)) == k - i):
                        self._send_reports_num_quant(f, POS, n, f_sbst, rui, cqch)

    def _send_reports_num_quant(self, f: Frame, sign: str, n: int, f_sbst: tuple, old_rui: RUI,
                                cqch: Cqch) -> None:
        node = f.NODE
        ch = cqch.channel
        ptree, _adj, node_ruiset = cqch.ruiset
        destn = ch.destination
        ant_ptree = ptree[0]
        ruiset = _assoc_value(ptree, node_ruiset)
        for rui in _assoc_value(ant_ptree, node_ruiset):
            restr = rui.subst
            q_sbst = sbst_restrict(rui.subst, node.quantified_vars())
            pos_i = _select_instances(f_sbst, f.NUM_QUANT_POS_INSTANCES)
            neg_i = _select_instances(f_sbst, f.NUM_QUANT_NEG_INSTANCES)
            if (sbst_is_compatible(f_sbst, rui.subst)
                    and not sbst_set_member(q_sbst, ordered_union(pos_i, neg_i, _sub_equal))):
                if sign == POS:
                    f.NUM_QUANT_POS_INSTANCES = _update_instances(f_sbst, q_sbst,
                                                                  f.NUM_QUANT_POS_INSTANCES)
                    self._inform_num_quant(f, POS, f_sbst, restr, neg_i, destn)
                else:
                    f.NUM_QUANT_NEG_INSTANCES = _update_instances(f_sbst, q_sbst,
                                                                  f.NUM_QUANT_NEG_INSTANCES)
                    self._inform_num_quant(f, NEG, f_sbst, restr, pos_i, destn)
                self.send_reports([Report(sbst_restrict(rui.subst, destn.get_freevars()),
                                          self._support_num_quant(f, ch, old_rui, rui, ruiset,
                                                                  n, sign),
                                          sign, node, None, ch.context)], ch)

    def _inform_num_quant(self, f: Frame, sign: str, f_sbst: tuple, restr: Any,
                          instances: list, destn: Node) -> None:
        self.remark("\nSince", (f.NODE,), f_sbst)
        for inst in instances:
            self.remark("and it is not the case that" if sign == POS else "and", (destn,),
                        sbst_union(inst, f_sbst))
        self.remark("I infer" if sign == POS else "I infer it is not the case that",
                    (destn,), restr)

    def _support_num_quant(self, f: Frame, ch: Any, old_rui: RUI, rui: RUI, rui_set: list,
                           n: int, sign: str) -> tuple:
        node = f.NODE
        f_sbst = sbst_restrict(rui.subst, node.get_freevars())
        fns: list = []
        for r in rui_set:
            if (sbst_is_compatible(f_sbst, r.subst)
                    and r.poscount == (n if sign == POS else n + 1)
                    and r.negcount == (1 if sign == POS else 0)):
                fns = ordered_union(list(r.fns), fns, lambda a, b: a is b)
        fns = ordered_union(list(old_rui.fns), ordered_union(list(rui.fns), fns, lambda a, b: a is b),
                       lambda a, b: a is b)
        return self._support_combination(f, ch, fns, rui.subst)

    # -- acting rules --------------------------------------------------------
    def rule_handler_do_if(self, f: Frame, ant_act: Any, cqch: Any) -> bool:
        node = f.NODE
        sensory_act = self.applysubst(tuple(ant_act)[0], cqch.filter)
        self.remark("\nSince", (node,), None)
        self.remark("\nI will perform", (sensory_act,), None)
        self.activate_n(sensory_act)
        pr = self.activation_n(sensory_act)
        pr.slots["PRIORITY"] = INTEND
        pr.slots["AGENDA"] = "START"
        self.schedule(pr, self.act_queue)
        return True

    def _schedule_reaction(self, f: Frame, ant_report: Report, cqch: Cqch, rui: RUI) -> Node:
        node = f.NODE
        restr = rui.subst
        ch = cqch.channel
        reactionset = self.apply_subst_ns(restr, (ch.destination,))
        reaction = reactionset[0]
        if not rui.remarkedp:
            self.remark("\nSince", (node,), restr)
            self.remark("and", (ant_report.signature,), restr)
            self.remark("I will perform", reactionset, None)
        if not reaction.nodeset("action"):
            raise SNePSError(f"The supposed ACT node {reaction} does not have an ACTION.")
        self.activate_act_n(reaction)
        pr = self.activation_n(reaction)
        pr.slots["PRIORITY"] = INTEND
        pr.slots["AGENDA"] = "START"
        self.schedule(pr, self.act_queue)
        return reaction

    def rule_handler_when_do(self, f: Frame, ant_report: Report, cqch: Cqch) -> bool:
        node = f.NODE
        for rui in self._ruis_for(f, ant_report, cqch):
            if ant_report.sign == POS and rui.poscount >= 1:
                self._schedule_reaction(f, ant_report, cqch, rui)
                if self.isassert(node) and self.sv_contains("assertions", node):
                    self.remove_hyps_silently((node,), self.crntct)
        return True

    def rule_handler_whenever_do(self, f: Frame, ant_report: Report, cqch: Cqch) -> Any:
        node = f.NODE
        if not self.isassert(node):
            return None
        for rui in self._ruis_for(f, ant_report, cqch):
            if ant_report.sign == POS and rui.poscount >= 1:
                self._schedule_reaction(f, ant_report, cqch, rui)
        return True

    def rule_handler_non_deriv(self, f: Frame, ant_report: Any, cqch: Any) -> None:
        return None

    def apply_subst_ns(self, subst: Any, nodeset: Any) -> tuple:
        out: tuple = ()
        for n in nodeset:
            out = ns_insert(self.applysubst(n, subst), out)
        return out

    # ------------------------------------------------------------------
    # usability tests
    @staticmethod
    def _quant_ok(node: Node, rel: str = "forall") -> bool:
        return not node.quantified_vars() or bool(node.nodeset(rel))

    RULE_HANDLERS = {
        "rule-handler.v-ent": lambda self, f, a, b: self.rule_handler_v_ent(f, a, b),
        "rule-handler.&-ent": lambda self, f, a, b: self.rule_handler_and_ent(f, a, b),
        "rule-handler.thresh": lambda self, f, a, b: self.rule_handler_thresh(f, a, b),
        "rule-handler.nor": lambda self, f, a, b: self.rule_handler_nor(f, a, b),
        "rule-handler.and": lambda self, f, a, b: self.rule_handler_and(f, a, b),
        "rule-handler.and-or": lambda self, f, a, b: self.rule_handler_and_or(f, a, b),
        "rule-handler.num-ent": lambda self, f, a, b: self.rule_handler_num_ent(f, a, b),
        "rule-handler.num-quant": lambda self, f, a, b: self.rule_handler_num_quant(f, a, b),
        "rule-handler.non-deriv": lambda self, f, a, b: self.rule_handler_non_deriv(f, a, b),
        "rule-handler.do-if": lambda self, f, a, b: self.rule_handler_do_if(f, a, b),
        "rule-handler.when-do": lambda self, f, a, b: self.rule_handler_when_do(f, a, b),
        "rule-handler.whenever-do": lambda self, f, a, b: self.rule_handler_whenever_do(f, a, b),
    }

    USABILITY_TESTS = {
        "usability-test.v-ent": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.&-ent": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.thresh": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.and-or": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.num-ent": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.and": lambda self, f, s: self._quant_ok(f.NODE),
        "usability-test.nor": lambda self, f, s: self._quant_ok(f.NODE),
        "usability-test.num-quant": lambda self, f, s: s == POS and self._quant_ok(f.NODE, "pevb"),
        "usability-test.non-deriv": lambda self, f, s: False,
        "usability-test.do-if": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.when-do": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
        "usability-test.whenever-do": lambda self, f, s: s == POS and self._quant_ok(f.NODE),
    }


def _null_out() -> Any:
    from ..io.streams import NullOutputStream
    return NullOutputStream()


def _get_compatible_ruis(ruis1: list, ruis2: list) -> list:
    out: list = []
    if ruis1 and ruis2:
        for r1 in ruis1:
            for r2 in ruis2:
                if sbst_is_compatible(r1.subst, r2.subst):
                    out = ruis_update(RUI(sbst_union(r1.subst, r2.subst),
                                          r1.poscount + r2.poscount, r1.negcount + r2.negcount,
                                          tuple(r1.fns) + tuple(r2.fns), r2.remarkedp), out)
    return out


def _get_new_ruis(ruis1: list, ruis2: list) -> list:
    out: list = []
    for r in ruis1:
        if not any(sbst_eq(r.subst, r2.subst) and rui_compatible(r, r2) for r2 in ruis2):
            out = [r] + out
    return out


def _combinations_fns(k: int, fns: tuple, otherfns: tuple) -> list:
    combos: list = []
    if k == 1:
        for fn in fns:
            combos = [(fn,) + tuple(otherfns)] + combos
    else:
        rest = tuple(fns)
        for fn in fns:
            rest = rest[1:]
            combos = combos + [(fn,) + c for c in _combinations_fns(k - 1, rest, otherfns)]
    return combos


def _update_instances(f_sbst: tuple, q_sbst: tuple, lst: Any) -> list:
    lst = list(lst or [])
    if not lst:
        return [[f_sbst, [q_sbst]]]
    first = lst[0]
    if sbst_eq(f_sbst, first[0]):
        return [[f_sbst, ordered_union([q_sbst], list(first[1]), _sub_equal)]] + lst[1:]
    return [first] + _update_instances(f_sbst, q_sbst, lst[1:])


def _select_instances(f_sbst: tuple, lst: Any) -> list:
    for entry in lst or []:
        if sbst_eq(f_sbst, entry[0]):
            return list(entry[1])
    return []
