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
"""The SNePS Inference Package, SNIP (``snip/fns/*``).

Inference is carried out by processes attached to nodes, which exchange
requests (sent backward along channels) and reports (sent forward).  This
module holds node activation, message passing, the non-rule and rule node
processes, rule introduction, the user processes and the ``deduce`` and
``add`` entry points.  The rule handlers are in :mod:`.handlers` and the
acting system in :mod:`.acting`.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Iterable, Optional

from ..core.node import Node
from ..core.nodeset import (ctcs_get, ctcs_insert, ns_compl, ns_insert, ns_ismemb, ns_remove,
                            ns_union)
from ..core.network import SNePSError
from ..match.unify import restrict_binding_to_pat, violates_uvbr
from .multi import HIGH, LOW, Frame, Process, StopInference
from .structs import (FALSE, NEG, OPEN, POS, REQUESTED, SENSOR, TRUE, UNKNOWN, USER, RUI, Channel,
                      Cqch, Feeder, Ich, Instance, Report, build_ptree, ch_equivalent,
                      chset_insert, compatible, cqchset_insert, cqchset_update, feedset_insert,
                      filter_ok, fns_flag, fns_support, fns_update, get_var_bindings,
                      ichset_insert, ichset_update, iset_insert, mb_equal, nodeset_to_fnodeset,
                      ptree_to_adj_list, repset_insert, repset_union, request_all,
                      restr_equivalent, rui_update, ruis_update, sbst_binding, sbst_is_compatible,
                      sbst_issubset, sbst_putin, sbst_restrict, sbst_union, change_tag_support,
                      combine_ots_star, combine_and_intr_ots_star, combinations_of,
                      fns_to_suplist, non_hyp, sup_included, sup_to_combinations)

RULE_TYPES = {
    "or-entailment": ("rule-handler.v-ent", "usability-test.v-ent"),
    "and-entailment": ("rule-handler.&-ent", "usability-test.&-ent"),
    "thresh": ("rule-handler.thresh", "usability-test.thresh"),
    "nor": ("rule-handler.nor", "usability-test.nor"),
    "and": ("rule-handler.and", "usability-test.and"),
    "and-or": ("rule-handler.and-or", "usability-test.and-or"),
    "num-entailment": ("rule-handler.num-ent", "usability-test.num-ent"),
    "num-quantifier": ("rule-handler.num-quant", "usability-test.num-quant"),
    "non-derivable": ("rule-handler.non-deriv", "usability-test.non-deriv"),
    "do-if": ("rule-handler.do-if", "usability-test.do-if"),
    "when-do": ("rule-handler.when-do", "usability-test.when-do"),
    "whenever-do": ("rule-handler.whenever-do", "usability-test.whenever-do"),
}


def _restr_subst(restr: Any) -> tuple:
    """SUBST.RESTR: restrictions are represented by their substitution."""
    return tuple(restr or ())


class SnipMixin:
    """SNIP, mixed into :class:`~sneps.Network`."""

    def _init_snip(self) -> None:
        self._init_multi()
        self.user_process: Optional[Process] = None
        self.added_nodes: tuple = ()
        self.deduction_results: Any = ()
        self.depth_cutoff_back: Optional[int] = 10
        self.depth_cutoff_forward: Optional[int] = 10
        self.use_intensional_contexts = True
        self.attached_functions: dict = {}
        self.primitive_action_functions: dict = {}
        self.gentemp_counter = 0
        self.snepslog_running = False

    # ------------------------------------------------------------------
    # small helpers
    def ctx(self, ct: Any) -> Any:
        """The context designated by CT (a context or a context name)."""
        if ct is None:
            return None
        if isinstance(ct, str):
            return self.get_context(ct)
        return ct

    def filter_sup(self, sup: tuple, ct: Any) -> tuple:
        from ..core.nodeset import ctcs_filter
        c = self.ctx(ct)
        return ctcs_filter(sup, c) if c is not None else ()

    def issubset_ctx(self, c1: Any, c2: Any) -> bool:
        a, b = self.ctx(c1), self.ctx(c2)
        if a is None or b is None:
            return False
        return self.issubset_ct(a, b)

    def gentemp(self, prefix: str) -> str:
        while True:
            self.gentemp_counter += 1
            name = f"{prefix}{self.gentemp_counter}"
            if not self.is_sv(name):
                return name

    def all_vars(self, n: Node) -> tuple:
        return ns_union(n.get_freevars(), n.quantified_vars())

    def reset_attachments(self) -> None:
        self.attached_functions = {}
        self.primitive_action_functions = {}

    # ------------------------------------------------------------------
    # activation (node2, transformers, make)
    def activate_n(self, n: Node) -> None:
        if n.activation is None:
            n.activation = self.node_to_process(n)

    def activation_n(self, n: Node) -> Process:
        self.activate_n(n)
        return n.activation

    def activate_act_n(self, n: Node) -> None:
        n.activation = self.make_act(n)

    def deactivate_n(self, n: Node) -> None:
        n.activation = None

    def node_to_process(self, n: Node) -> Process:
        if n.is_v_ent():
            return self._make_rule("or-entailment", n)
        if n.is_and_ent():
            return self._make_rule("and-entailment", n)
        if n.is_thresh():
            return self._make_rule("thresh", n)
        if n.is_nor():
            return self._make_rule("nor", n)
        if n.is_and():
            return self._make_rule("and", n)
        if n.is_and_or():
            return self._make_rule("and-or", n)
        if n.is_num_ent():
            return self._make_rule("num-entailment", n)
        if n.is_num_quant():
            h, t = RULE_TYPES["num-quantifier"]
            return Process("num-quant.rule", "num-quantifier", n, [], None, None, [], [], [],
                           [], [], [], [], None, h, t)
        if n.is_non_deriv():
            return self._make_rule("non-derivable", n)
        if n.is_do_if():
            return self._make_rule("do-if", n)
        if n.is_when_do():
            return self._make_rule("when-do", n)
        if n.is_whenever_do():
            return self._make_rule("whenever-do", n)
        if n.is_act():
            return self.make_act(n)
        return Process("non-rule", n, [], [], [], [], [], [], None)

    def _make_rule(self, rtype: str, n: Node) -> Process:
        h, t = RULE_TYPES[rtype]
        return Process("rule", rtype, n, [], [], [], [], [], [], [], [], None, h, t)

    def make_act(self, n: Node) -> Process:
        if not n.is_act():
            self.write(f"\nWARNING: *** The node {n} is being activated as an act, but it "
                       "doesn't look like an act to sneps:is-act.n. ***\n")
        return Process("act", n, None, (), (), (), (), None, None)

    def clear_infer_all(self) -> None:
        for n in self.all_nodes():
            self.deactivate_n(n)

    def clear_infer(self) -> None:
        """CLEAR-INFER: forget inference state, keeping rules' known instances."""
        for nde in self.all_nodes():
            p = nde.activation
            if p is None:
                continue
            typ = p.slots["NAME"]
            if typ in ("rule", "num-quant.rule"):
                known = p.slots["KNOWN_INSTANCES"]
                nde.activation = None
                p = self.activation_n(nde)
                p.slots["KNOWN_INSTANCES"] = known
            elif nde.is_act():
                pass
            else:
                self.deactivate_n(nde)
        self.gc_nodes()

    # ------------------------------------------------------------------
    # report and request kinds (report, request)
    @staticmethod
    def _sig_in(sender: Any, node: Node, rels: tuple) -> bool:
        return isinstance(sender, Node) and any(ns_ismemb(sender, node.nodeset(r)) for r in rels)

    def is_ant_to_rule_rep(self, rep: Report, node: Node) -> bool:
        return self._sig_in(rep.signature, node, ("ant", "arg", "when", "whenever", "&ant"))

    def is_cq_to_rule_rep(self, rep: Report, node: Node) -> bool:
        return self._sig_in(rep.signature, node, ("cq", "arg", "dcq"))

    def is_rule_to_cq_rep(self, rep: Report, node: Node) -> bool:
        return self._sig_in(rep.signature, node, ("cq-", "arg-", "dcq-"))

    def is_node_to_node_rep(self, rep: Report, node: Node) -> bool:
        return (isinstance(rep.signature, Node) and not self.is_ant_to_rule_rep(rep, node)
                and not self.is_rule_to_cq_rep(rep, node))

    def is_cq_to_rule_req(self, ch: Channel, node: Node) -> bool:
        return self._sig_in(ch.destination, node, ("cq", "arg", "if", "dcq"))

    def is_rule_to_cq_req(self, ch: Channel, node: Node) -> bool:
        return self._sig_in(ch.destination, node, ("cq-", "arg-"))

    def is_rule_to_ant_req(self, ch: Channel, node: Node) -> bool:
        return self._sig_in(ch.destination, node, ("ant-", "arg-", "&ant-"))

    @staticmethod
    def is_from_user_req(ch: Channel) -> bool:
        return ch.destination == USER

    # ------------------------------------------------------------------
    # consequents and antecedents
    @staticmethod
    def antecedents(rule: Node, cq: Any) -> tuple:
        if rule.is_and() or rule.is_nor():
            return ()
        return (rule.nodeset("ant") or rule.nodeset("&ant")
                or (rule.nodeset("do") if rule.nodeset("if") else ())
                or rule.nodeset("when") or rule.nodeset("whenever")
                or ns_remove(cq, rule.nodeset("arg")))

    @staticmethod
    def consequents(rule: Node, ant: Any) -> tuple:
        cqs = ns_union(rule.nodeset("cq"), ns_union(rule.nodeset("do"), rule.nodeset("dcq")))
        return cqs if cqs else ns_remove(ant, rule.nodeset("arg"))

    @staticmethod
    def all_consequents(rule: Node) -> tuple:
        cqs = ns_union(rule.nodeset("cq"), ns_union(rule.nodeset("do"), rule.nodeset("dcq")))
        return cqs if cqs else rule.nodeset("arg")

    @staticmethod
    def consequents_ent(rule: Node) -> tuple:
        return ns_union(rule.nodeset("cq"), rule.nodeset("dcq"))

    def is_all_pat_same_vars(self, pats: Iterable[Node]) -> bool:
        pats = tuple(pats or ())
        if not pats:
            return True
        vl = set(map(id, self.all_vars(pats[0])))
        return all(set(map(id, self.all_vars(p))) == vl for p in pats)

    # ------------------------------------------------------------------
    # messages
    def try_to_send_report(self, rep: Report, ch: Channel) -> Any:
        newsup = self.filter_sup(rep.support, ch.context)
        if newsup and filter_ok(rep.subst, ch.filter):
            return self.send_reports([Report(rep.subst, newsup, rep.sign, rep.signature,
                                             rep.node, rep.context)], ch)
        return None

    def send_reports(self, repset: list, ch: Channel) -> Any:
        d = ch.destination
        if d == USER:
            pr = self.user_process
            swrep = self.switch_reports(repset, ch)
            pr.slots["REPORTS"] = repset_union(pr.slots["REPORTS"], swrep)
            pr.slots["PRIORITY"] = HIGH
            self.initiate(pr)
            return swrep
        if self.depth_cutoff_forward:
            repset = self.filter_repset(repset)
        if repset:
            self.activate_n(d)
            pr = self.activation_n(d)
            swrep = self.switch_reports(repset, ch)
            pr.slots["REPORTS"] = repset_union(pr.slots["REPORTS"], swrep)
            pr.slots["PRIORITY"] = HIGH
            self.initiate(pr)
            return swrep
        return None

    def filter_repset(self, repset: list) -> list:
        out: list = []
        cutoff = self.depth_cutoff_forward
        for rep in repset:
            sig = rep.signature
            h = sig.height if isinstance(sig, Node) else 0
            if h > cutoff or _max_height_sub(rep.subst) > cutoff:
                self.remark(f"Forward inference cutoff of {sig}{{{_sstr(rep.subst)}}} beyond "
                            f"*depthcutoffforward* = {cutoff}\n", None, None)
            else:
                out = repset_insert(rep, out)
        return out

    def switch_reports(self, repset: list, ch: Channel) -> list:
        result: list = []
        for rep in repset:
            newrep = self.switch_one_report(rep, ch)
            if newrep is not None:
                result = repset_insert(newrep, result)
        return result

    def switch_one_report(self, rep: Report, ch: Channel) -> Optional[Report]:
        f = self.f
        name = getattr(f, "NAME", None) if f is not None else None
        rtype = getattr(f, "TYPE", None) if f is not None else None
        cur_node = getattr(f, "NODE", None) if f is not None else None
        d = ch.destination
        signature = rep.signature
        if d == USER:
            situation = "to-user"
        elif isinstance(signature, Node) and ns_ismemb(d, self.all_consequents(signature)):
            situation = "to-cq"
        elif self.is_ant_to_rule_rep(rep, d):
            situation = "to-rule"
        elif self.is_cq_to_rule_rep(rep, d):
            situation = "from-cq"
        else:
            situation = "to-nonrule"
        if situation == "to-nonrule":
            newsub = self.substitute_in_terms(ch.switch, rep.subst)
        elif situation in ("to-rule", "to-user", "from-cq"):
            newsub = tuple(rep.subst)
        else:
            from ..match.unify import initbind
            newsub = self.substitute_in_terms(initbind(d), rep.subst)
        if violates_uvbr(newsub):
            return None
        patnode = signature if situation in ("to-user", "to-rule", "from-cq") else d
        if patnode.quantified_vars():
            newnode = self.find_or_build(self.clean_quantifiers_cs(
                self.apply_subst_cs(newsub, self.n_to_downcs(patnode))))[0]
        else:
            newnode = self.applysubst(patnode, newsub)
        if situation in ("to-rule", "from-cq"):
            support = rep.support
        elif situation in ("to-user", "to-cq"):
            if (name == "rule" and rtype == "nor"
                    and self.instanciated_quantified_vars(signature, ch, newsub)):
                support = change_tag_support(rep.support)
            else:
                support = rep.support
        else:
            if (self.instanciated_quantified_vars(signature, ch, newsub)
                    or _nor_to_nor_with_different_args(signature, d)):
                support = change_tag_support(rep.support)
            else:
                support = rep.support
        if signature is not newnode:
            support = non_hyp(support)
        newsub = sbst_putin((patnode, newnode), newsub)
        if rep.sign == NEG:
            newnode = self.negate_n(newnode)
        if ((newnode.is_mol or newnode.is_pat)
                and not (name == "rule" and rtype == "nor" and rep.sign == NEG
                         and isinstance(signature, Node)
                         and len(self.all_consequents(signature)) == 1
                         and newnode is cur_node)):
            self.addsupport(support, newnode)
            self.ck_contradiction(newnode, ch.context, "snip")
        return Report(newsub, support, rep.sign, signature, newnode, rep.context)

    def apply_subst_cs(self, subst: Iterable, cs: list) -> list:
        """APPLY-SUBST.CS (note: reverses the cable order, as SNePS 2.8 does)."""
        out: list = []
        for r, ns in cs:
            new: tuple = ()
            for n in ns:
                new = ns_insert(self.applysubst(n, subst), new)
            out.insert(0, (r, new))
        return out

    def clean_quantifiers_cs(self, dcs: list) -> list:
        from ..core.build import cs_insert
        result: list = []
        for r, ns in dcs:
            varns = tuple(n for n in ns if n.is_var)
            if self.isquant_r(r):
                if varns:
                    result = cs_insert(result, r, varns)
            else:
                if varns:
                    q = varns[0].quantifier_of()
                    if q is not None:
                        result = cs_insert(result, q, varns)
                result = [(r, ns)] + result
        return result

    def install_channel(self, f: Frame, ch: Channel) -> None:
        f.OUTGOING_CHANNELS = chset_insert(ch, f.OUTGOING_CHANNELS)
        if ch.destination != USER:
            self.activate_n(ch.destination)

    @staticmethod
    def instanciated_quantified_vars(node: Any, ch: Channel, subst: Iterable) -> bool:
        if not isinstance(node, Node):
            return False
        vs = node.quantified_vars()
        if not vs:
            return False
        return (any(sbst_binding(v, ch.filter) is not None for v in vs)
                or any(sbst_binding(v, subst) is not None for v in vs))

    # ------------------------------------------------------------------
    # unknown instances (instance)
    def unknown_inst(self, f: Frame, inst: Instance) -> bool:
        for y in f.KNOWN_INSTANCES:
            if all(sbst_binding(p[0], y.subst) is p[1] for p in inst.subst) \
                    and sup_included(inst.support, y.support):
                return False
        return True

    # ------------------------------------------------------------------
    # non-rule node processes (non-rule, nrn-*)
    def p_non_rule(self, f: Frame) -> None:
        try:
            if self.use_one_queue_only:
                self.process_reports_non_rule(f)
                self.process_requests_non_rule(f)
                self.process_forward_inferences_non_rule(f)
            elif f.REPORTS:
                self.process_reports_non_rule(f)
            else:
                self.process_requests_non_rule(f)
                self.process_forward_inferences_non_rule(f)
        except StopInference:
            pass
        self.write_back(f)

    def process_reports_non_rule(self, f: Frame) -> None:
        reports = f.REPORTS
        f.REPORTS = []
        for r in reports:
            self.process_one_report_non_rule(f, r)
        if f.PENDING_FORWARD_INFERENCES:
            f.PRIORITY = LOW
            self.initiate(self.activation_n(f.NODE))

    def process_one_report_non_rule(self, f: Frame, report: Report) -> None:
        instance = Instance(report.subst, report.support, report.sign)
        if self.unknown_inst(f, instance):
            self.added_nodes = ns_insert(report.node, self.added_nodes)
            f.KNOWN_INSTANCES = iset_insert(instance, f.KNOWN_INSTANCES)
            if not self.broadcast_one_report(f, Report(report.subst, report.support,
                                                       report.sign, f.NODE, None,
                                                       report.context)):
                f.PENDING_FORWARD_INFERENCES = repset_insert(report,
                                                             f.PENDING_FORWARD_INFERENCES)

    def broadcast_one_report(self, f: Frame, rep: Report) -> Any:
        anysent = None
        for ch in list(f.OUTGOING_CHANNELS):
            if ch.is_open():
                anysent = self.try_to_send_report(rep, ch) or anysent
        return anysent

    def process_forward_inferences_non_rule(self, f: Frame) -> None:
        repset = f.PENDING_FORWARD_INFERENCES
        f.PENDING_FORWARD_INFERENCES = []
        for r in repset:
            self.process_one_forward_inference_non_rule(f, r)

    def process_one_forward_inference_non_rule(self, f: Frame, rep: Report) -> None:
        crntct = rep.context
        with self.let(crntct=crntct):
            sub = rep.subst
            node = f.NODE
            updated = Report(sub, rep.support, rep.sign, node, None, crntct)
            f.INCOMING_CHANNELS = feedset_insert(Feeder(sub, crntct, rep.signature, OPEN),
                                                 f.INCOMING_CHANNELS)
            self.push_forward(f, updated, self.in_context_ns(node.nodeset("ant-"), True))
            self.push_forward(f, updated, self.in_context_ns(node.nodeset("&ant-"), True))
            self.push_forward(f, updated, self.in_context_ns(node.nodeset("when-"), True))
            self.push_forward(f, updated, self.in_context_ns(node.nodeset("whenever-"), True))
            self.push_forward(f, updated, self.in_context_ns(
                [n for n in node.nodeset("arg-") if not (n.is_and() or n.is_nor())], True))
            numq = [r for r in node.nodeset("cq-") if r.is_num_quant()]
            self.push_forward(f, updated, self.in_context_ns(numq, True))
            if not self.is_node_to_node_rep(rep, node):
                for m in self.forward_match_in_context(node, crntct, sub):
                    if m[0] is not node:
                        ch = Channel(m[1], m[3], crntct, m[0], OPEN)
                        self.install_channel(f, ch)
                        self.send_reports([updated], ch)

    def push_forward(self, f: Frame, report: Report, nodeset: Iterable[Node]) -> None:
        for n in nodeset:
            ch = Channel((), (), report.context, n, OPEN)
            self.install_channel(f, ch)
            self.send_reports([report], ch)

    def process_requests_non_rule(self, f: Frame) -> None:
        requests = f.REQUESTS
        st = {"remark_sent": False, "pathfrom_result": None}
        f.REQUESTS = []
        for ch in requests:
            self.process_one_request_non_rule(f, ch, st)

    def process_one_request_non_rule(self, f: Frame, ch: Channel, st: dict) -> None:
        node = f.NODE
        self.install_channel(f, ch)
        if self.isassert(node, ch.context):
            self.process_request_of_asserted_node(f, ch, st)
            return
        if self.procedural_attachment_p(node):
            self.process_request_of_attached_node(f, ch)
        crntct = ch.context
        with self.let(crntct=crntct):
            restr = None
            any_sent = self.send_known_instances(f, ch)
            if not any_sent or self.is_wh_question(f, ch.filter):
                restr = ch.filter
                if self.not_working_on(f, restr, crntct, ch):
                    self.send_rule_use_requests(f, restr, crntct, ch.destination, st)
                    if (self.is_rule_to_ant_req(ch, node) or self.is_rule_to_cq_req(ch, node)
                            or self.is_from_user_req(ch)):
                        self.remark("\nI wonder if", (node,), restr, ch.context)
                        self.send_node_to_node_requests(f, restr, crntct)
                if (self.is_case_of_introduction(f, ch)
                        and self.not_working_on_introduction(f, restr, crntct)):
                    self.initiate_introduction_rule(f, ch)

    def process_request_of_asserted_node(self, f: Frame, ch: Channel, st: dict) -> None:
        crntct = ch.context
        with self.let(crntct=crntct):
            if not st["remark_sent"]:
                self.remark("\nI know", (f.NODE,), None)
                st["remark_sent"] = True
            self.send_reports([Report((), self.filter_sup(f.NODE.asupport, crntct), POS,
                                      f.NODE, None, crntct)], ch)

    def is_wh_question(self, f: Frame, substitution: Iterable) -> bool:
        for v in f.NODE.get_freevars():
            b = sbst_binding(v, substitution)
            if b is None or not isinstance(b, Node) or b.is_var or b.is_pat:
                return True
        return False

    def send_request(self, req: Channel, n: Node, restr: Any) -> None:
        cutoff = self.depth_cutoff_back
        if cutoff and (n.height > cutoff or _max_height_sub(req.filter) > cutoff):
            self.remark(f"SNIP depth cutoff beyond *depthcutoffback* = {cutoff}\n", None, None)
            return
        self.activate_n(n)
        pr = self.activation_n(n)
        if pr.slots["NAME"] == "num-quant.rule":
            qv = pr.slots["NODE"].quantified_vars()
            s = _restr_subst(restr)
            new_sbst = tuple(mb for mb in s if not any(mb_equal(mb, x)
                                                       for x in sbst_restrict(s, qv)))
            restr = new_sbst
            req = Channel(new_sbst, req.switch, req.context, req.destination, req.valve)
        pr.slots["REQUESTS"] = chset_insert(req, pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        f = self.f
        f.INCOMING_CHANNELS = feedset_insert(Feeder(restr, req.context, n, req.valve),
                                             f.INCOMING_CHANNELS)
        self.initiate(pr)

    def send_known_instances(self, f: Frame, ch: Channel) -> bool:
        sent = False
        for inst in list(f.KNOWN_INSTANCES):
            if self.try_to_send_report(Report(inst.subst, inst.support, inst.sign, f.NODE,
                                              None, ch.context), ch):
                sent = True
        return sent

    def not_working_on(self, f: Frame, restr: Any, ct: Any, ch: Channel) -> bool:
        node = f.NODE
        special = (self.is_rule_to_ant_req(ch, node) or self.is_rule_to_cq_req(ch, node)
                   or self.is_from_user_req(ch))
        for feeder in f.INCOMING_CHANNELS:
            if (restr_equivalent(restr, feeder.restriction)
                    and self.issubset_ctx(ct, feeder.context)):
                if special:
                    src = feeder.source
                    if not (ns_ismemb(src, node.nodeset("cq-"))
                            or ns_ismemb(src, node.nodeset("arg-"))):
                        return False
                else:
                    return False
        return True

    def send_rule_use_requests(self, f: Frame, restriction: Any, context: Any,
                               prev_requester: Any, st: dict) -> None:
        node = f.NODE
        out = Channel(_restr_subst(restriction), (), context, node, OPEN)
        if st.get("pathfrom_result") is None:
            st["pathfrom_result"] = self.pathfrom(["or", "cq-", "arg-", "dcq-", "if-"], node)
        targets = st["pathfrom_result"]
        if prev_requester != USER:
            targets = ns_remove(prev_requester, targets)
        self.broadcast_request(out, targets, restriction)

    def broadcast_request(self, req: Channel, ns: Iterable[Node], restr: Any) -> bool:
        for n in ns:
            self.send_request(req, n, restr)
        return True

    def send_node_to_node_requests(self, f: Frame, restriction: Any, context: Any) -> None:
        node = f.NODE
        rsbst = _restr_subst(restriction)
        rnode = self.applysubst(node, rsbst)
        if self.isassert(rnode, context):
            self.send_request(Channel((), rsbst, context, node, OPEN), rnode, restriction)
            return
        for m in self.match_in_context(node, context, rsbst):
            tnode, tsbst, ssbst = m[0], m[1], m[3]
            if not (tnode is node or (tnode.is_pat and self.is_mgci_asserted(tnode, tsbst))):
                self.send_request(Channel(tsbst, ssbst, context, node, OPEN), tnode, restriction)

    def is_mgci_asserted(self, tnode: Node, tsbst: Iterable) -> bool:
        mgci = self.applysubst(tnode, tsbst)
        return not mgci.is_pat and (self.isassert(mgci) or self.isassert(self.negate_n(mgci)))

    # -- procedural attachment ----------------------------------------------
    def procedural_attachment_p(self, node: Node) -> bool:
        fns = node.nodeset("attachedfunction")
        return bool(fns) and fns[0] in self.attached_functions

    def attach_function(self, node: Node, fn: Any) -> None:
        """Attach the Python callable FN to the predicate node NODE."""
        self.attached_functions[node] = fn
        self.set_sv("attached-functions",
                    ns_insert(node, self.value_sv("attached-functions") or ()))

    def execute_attached_function(self, node: Node, subst: Iterable) -> Any:
        fn = self.attached_functions[node.nodeset("attachedfunction")[0]]
        return fn(self, self.applysubst(node, subst))

    def ns_to_attachment_arg(self, ns: Iterable[Node]) -> list:
        out: list = []
        for n in ns:
            out.insert(0, n if n.is_var else self.node_value(n))
        return out

    def node_value(self, n: Node) -> Any:
        return n.value

    def nodize_sub_terms(self, subst: Iterable) -> tuple:
        out = []
        for var, trm in subst or ():
            if isinstance(trm, Node) or trm is None:
                out.append((var, trm))
            else:
                out.append((var, self.value_to_node(trm)))
        return tuple(out)

    def process_request_of_attached_node(self, f: Frame, ch: Channel) -> None:
        node = f.NODE
        for sign, sub in self.execute_attached_function(node, ch.filter) or ():
            if not sign:
                continue
            sign = str(sign).upper()
            crntct = ch.context
            with self.let(crntct=crntct):
                newsub = sbst_union(self.nodize_sub_terms(sub), ch.filter)
                newnode = self.applysubst(node, newsub)
                if sign == POS:
                    if newnode.is_pat:
                        raise SNePSError("Improper attempt by an attached function to assert "
                                         f"the pattern node {newnode}")
                    self.remark("\nI figure", (newnode,), None)
                    self.assert_n(newnode, crntct)
                elif sign == NEG:
                    if newnode.is_pat:
                        raise SNePSError("Improper attempt by an attached function to assert "
                                         f"the negation of the pattern node {newnode}")
                    self.remark("\nI figure it is not the case that", (newnode,), None)
                    res = self.topsneval(lambda n=newnode: self.assert_built(
                        [("min", 0), ("max", 0), ("arg", n)]))
                    newnode = res.value[0] if res.value else self.negate_n(newnode)
                self.send_reports([Report(newsub, self.filter_sup(newnode.asupport, crntct),
                                          sign, node, None, crntct)], ch)

    # ------------------------------------------------------------------
    # rule node processes (rule, rule-reports, rule-requests,
    # rule-finfers)
    def p_rule(self, f: Frame) -> None:
        try:
            if self.use_one_queue_only:
                self.process_reports_rule(f)
                self.process_requests_rule(f)
                self.process_forward_inferences_rule(f)
            elif f.REPORTS:
                self.process_reports_rule(f)
            else:
                self.process_requests_rule(f)
                self.process_forward_inferences_rule(f)
        except StopInference:
            pass
        self.write_back(f)

    def process_reports_rule(self, f: Frame) -> None:
        reports = f.REPORTS
        f.REPORTS = []
        for r in reports:
            self.process_one_report_rule(f, r)
        if f.PENDING_FORWARD_INFERENCES:
            f.PRIORITY = LOW
            self.initiate(self.activation_n(f.NODE))

    def process_one_report_rule(self, f: Frame, report: Report) -> None:
        node = f.NODE
        ant_to_rule = self.is_ant_to_rule_rep(report, node)
        cq_to_rule = self.is_cq_to_rule_rep(report, node)
        if cq_to_rule and f.TYPE == "num-quantifier":
            self.process_one_ant_report_rule(f, report)
        elif cq_to_rule and ant_to_rule:
            self.process_one_special_report_rule(f, report)
        elif ant_to_rule:
            self.process_one_ant_report_rule(f, report)
        elif cq_to_rule:
            self.process_one_introduction_report_rule(f, report)
        else:
            self.process_one_instance_report_rule(f, report)

    def process_one_instance_report_rule(self, f: Frame, report: Report) -> None:
        instance = Instance(report.subst, report.support, report.sign)
        if self.unknown_inst(f, instance):
            self.added_nodes = ns_insert(report.node, self.added_nodes)
            if instance.subst:
                f.KNOWN_INSTANCES = iset_insert(instance, f.KNOWN_INSTANCES)
            used = self.broadcast_one_report(f, Report(report.subst, report.support,
                                                       report.sign, f.NODE, None,
                                                       report.context))
            used = self.try_applying_one_report(f, report) or used
            if not used and self.usability_test(f, report.sign):
                f.PENDING_FORWARD_INFERENCES = repset_insert(report,
                                                             f.PENDING_FORWARD_INFERENCES)

    def process_one_ant_report_rule(self, f: Frame, report: Report) -> None:
        if not self.broadcast_ant_report_rule(f, report):
            f.PENDING_FORWARD_INFERENCES = repset_insert(report, f.PENDING_FORWARD_INFERENCES)

    def process_one_special_report_rule(self, f: Frame, report: Report) -> None:
        used = self.broadcast_ant_report_rule(f, report)
        used = self.process_one_introduction_report_rule(f, report) or used
        if not used:
            f.PENDING_FORWARD_INFERENCES = repset_insert(report, f.PENDING_FORWARD_INFERENCES)

    def broadcast_ant_report_rule(self, f: Frame, report: Report) -> Any:
        anysent = None
        for cqch in list(f.RULE_USE_CHANNELS):
            anysent = self.try_to_send_cq_report_rule(f, report, cqch) or anysent
        return anysent

    def usability_test(self, f: Frame, sign: str) -> bool:
        return self.USABILITY_TESTS[f.USABILITY_TEST](self, f, sign)

    def rule_handler(self, f: Frame, a: Any, b: Any) -> Any:
        return self.RULE_HANDLERS[f.RULE_HANDLER](self, f, a, b)

    def try_applying_one_report(self, f: Frame, report: Report) -> Any:
        if not self.usability_test(f, report.sign):
            return None
        inst = Instance(report.subst, report.support, report.sign)
        any_applied = None
        for cqch in list(f.RULE_USE_CHANNELS):
            if self.filter_sup(report.support, cqch.channel.context):
                if ((f.TYPE == "do-if"
                     and self.rule_handler(f, self.antecedents(f.NODE, None),
                                           Channel(report.subst, None, report.context, (),
                                                   OPEN)))
                        or (f.TYPE in ("and", "nor")
                            and self.try_to_send_cq_report_rule(f, report, cqch))
                        or self.try_to_apply_instance_rule(f, inst, cqch)):
                    any_applied = True
        return any_applied

    def try_to_apply_instance_rule(self, f: Frame, instance: Instance, cqch: Cqch) -> Any:
        if self.acceptable_rule_instances(instance, cqch.channel):
            return self.send_ant_requests_rule(f, cqch, instance.subst)
        return None

    def send_ant_requests_rule(self, f: Frame, cqch: Cqch, subst: Any = None) -> bool:
        ch, ants, ruis = cqch.channel, cqch.ants, cqch.ruiset
        if not (f.TYPE in ("and-entailment", "num-quantifier") or self.is_all_pat_same_vars(ants)):
            f.RULE_USE_CHANNELS = cqchset_update(Cqch(ch, ants, request_all(ruis)),
                                                 f.RULE_USE_CHANNELS)
        return self.broadcast_ant_request(f, ch, ants, ch.filter, subst)

    def broadcast_ant_request(self, f: Frame, req: Channel, ns: Iterable[Node], restr: Any,
                              subst: Any) -> bool:
        reqsubst = req.filter
        for n in ns:
            filt = []
            for v in n.get_freevars():
                term = sbst_binding(v, reqsubst)
                if term is None:
                    term = sbst_binding(v, subst)
                if term is not None:
                    filt.append((v, term))
            self.send_request(Channel(tuple(filt), (), req.context, f.NODE, OPEN), n, restr)
        return True

    def acceptable_rule_instances(self, inst: Instance, ch: Channel) -> bool:
        return compatible(inst.subst, ch.filter) and bool(self.filter_sup(inst.support,
                                                                          ch.context))

    def try_to_send_cq_report_rule(self, f: Frame, report: Report, cqch: Cqch) -> Any:
        repset = self._acceptable_versions(report, cqch.channel)
        crntct = cqch.channel.context
        with self.let(crntct=crntct):
            if not repset:
                return None
            node = f.NODE
            if self.isassert(node):
                if self.usability_test(f, POS):
                    return self.try_to_draw_conclusions_rule(f, repset, cqch)
                return None
            updated = cqch
            for inst in list(f.KNOWN_INSTANCES):
                if (sbst_issubset(sbst_restrict(sbst_union(report.subst, cqch.channel.filter),
                                                node.get_freevars()), inst.subst)
                        and self.usability_test(f, inst.sign)):
                    self.try_to_draw_conclusions_rule(
                        f, _fill_out_report_substs(repset, inst.subst), updated)
                updated = _get_updated_cqch(cqch, f.RULE_USE_CHANNELS) or updated
            return True

    def _acceptable_versions(self, rep: Report, ch: Channel) -> list:
        if compatible(rep.subst, ch.filter) and self.filter_sup(rep.support, ch.context):
            return [rep]
        return []

    def try_to_draw_conclusions_rule(self, f: Frame, repset: list, cqch: Cqch) -> bool:
        for rep in repset:
            self.rule_handler(f, rep, cqch)
        return True

    def process_requests_rule(self, f: Frame) -> None:
        st = {"remark_sent": False, "pathfrom_result": None}
        for ch in list(f.REQUESTS):
            if self.is_cq_to_rule_req(ch, f.NODE):
                self.process_rule_use_request_rule(f, ch, st)
            else:
                self.process_one_request_non_rule(f, ch, st)
        f.REQUESTS = []

    def process_rule_use_request_rule(self, f: Frame, request: Channel, st: dict) -> None:
        cqch = self.install_rule_use_channel(f, request)
        node = f.NODE
        sup = node.asupport
        filt = request.filter
        dest = request.destination
        crntct = request.context
        with self.let(crntct=crntct):
            if self.isassert(node) and self.usability_test(f, POS):
                if f.TYPE in ("and", "nor"):
                    self.rule_handler(f, Report(filt, sup, POS, dest, None, crntct), cqch)
                elif f.TYPE == "do-if":
                    self.rule_handler(f, self.antecedents(node, dest), request)
                else:
                    self.send_ant_requests_rule(f, cqch)
            else:
                rule_sbst = restrict_binding_to_pat(filt, node)
                if self.is_wh_question(f, rule_sbst) or not self.apply_known_rule_instance(f, cqch):
                    restr = rule_sbst
                    if self.not_working_on(f, restr, crntct, request):
                        self.send_rule_use_requests(f, restr, crntct, dest, st)

    def apply_known_rule_instance(self, f: Frame, cqch: Cqch) -> bool:
        found = False
        for inst in list(f.KNOWN_INSTANCES):
            if self.acceptable_rule_instances(inst, cqch.channel):
                found = True
                if f.TYPE == "num-quantifier":
                    self.send_ant_requests_rule(f, cqch)
        return found

    def install_rule_use_channel(self, f: Frame, request: Channel) -> Cqch:
        node = f.NODE
        dest = request.destination
        destsub = restrict_binding_to_pat(request.filter, dest)
        ch = Channel(destsub, request.switch, request.context, dest, request.valve)
        ants = self.antecedents(node, dest)
        if f.TYPE == "num-quantifier":
            cqs = node.nodeset("cq")
            ptree = [build_ptree(ants, self.all_vars), build_ptree(cqs, self.all_vars)]
            cqch = Cqch(ch, tuple(ants) + tuple(cqs), [ptree, ptree_to_adj_list(ptree), []])
        elif not ants or self.is_all_pat_same_vars(ants):
            cqch = Cqch(ch, ants, [])
        elif f.TYPE == "and-entailment":
            ptree = build_ptree(ants, self.all_vars)
            cqch = Cqch(ch, ants, [ptree, ptree_to_adj_list(ptree), []])
        else:
            cqch = Cqch(ch, ants, [RUI(destsub, 0, 0, nodeset_to_fnodeset(ants), False)])
        f.RULE_USE_CHANNELS = cqchset_insert(cqch, f.RULE_USE_CHANNELS)
        self.activate_n(dest)
        return cqch

    def process_forward_inferences_rule(self, f: Frame) -> None:
        repset = f.PENDING_FORWARD_INFERENCES
        f.PENDING_FORWARD_INFERENCES = []
        for r in repset:
            self.process_one_forward_inference_rule(f, r)

    def process_one_forward_inference_rule(self, f: Frame, report: Report) -> None:
        node = f.NODE
        if not self.is_there_rule_instance_forward(f, report):
            self.set_up_rule_use_channels(f, report)
            if (self.is_ant_to_rule_rep(report, node)
                    or (f.TYPE == "num-quantifier" and self.is_cq_to_rule_rep(report, node))):
                f.INCOMING_CHANNELS = feedset_insert(
                    Feeder(report.subst, report.context, report.signature, OPEN),
                    f.INCOMING_CHANNELS)
                self.broadcast_ant_report_rule(f, report)
            else:
                self.process_one_forward_inference_non_rule(f, report)
                self.try_applying_one_report(f, report)
        if not self.isassert(node):
            rule_sbst = restrict_binding_to_pat(report.subst, node)
            st = {"remark_sent": False, "pathfrom_result": None}
            self.send_rule_use_requests(f, rule_sbst, self.crntct, USER, st)

    def is_there_rule_instance_forward(self, f: Frame, report: Report) -> bool:
        all_args = f.NODE.nodeset("arg")
        checked = False
        if (all_args and self.is_all_pat_same_vars(all_args)) or f.TYPE == "num-quantifier":
            for inst in list(f.KNOWN_INSTANCES):
                if (compatible(get_var_bindings(inst.subst), get_var_bindings(report.subst))
                        and self.filter_sup(inst.support, report.context)):
                    checked = True
        return checked

    def set_up_rule_use_channels(self, f: Frame, report: Report) -> None:
        node = f.NODE
        subst, signature, ct = report.subst, report.signature, report.context
        if f.TYPE == "num-quantifier":
            ants = node.nodeset("&ant")
            cq = node.nodeset("cq")
            ptree = [build_ptree(ants, self.all_vars), build_ptree(cq, self.all_vars)]
            ch = Channel((), (), ct, cq[0] if cq else None, OPEN)
            cqch = Cqch(ch, tuple(ants) + tuple(cq), [ptree, ptree_to_adj_list(ptree), []])
            f.RULE_USE_CHANNELS = cqchset_insert(cqch, f.RULE_USE_CHANNELS)
            self.send_ant_requests_rule(f, cqch)
        elif self.is_all_pat_same_vars(node.nodeset("ant") or node.nodeset("when")
                                       or node.nodeset("whenever") or node.nodeset("&ant")
                                       or node.nodeset("arg")):
            cqs = (self.consequents(node, signature) if self.is_ant_to_rule_rep(report, node)
                   else self.all_consequents(node))
            for cq in cqs:
                ants = self.antecedents(node, cq)
                chsub = restrict_binding_to_pat(subst, cq)
                ch = Channel(subst, chsub, ct, cq, OPEN)
                cqch = Cqch(ch, ants, [])
                f.RULE_USE_CHANNELS = cqchset_insert(cqch, f.RULE_USE_CHANNELS)
                if not (f.TYPE == "or-entailment" and self.is_ant_to_rule_rep(report, node)):
                    self.send_ant_requests_rule(f, cqch)
        elif f.TYPE == "and-entailment":
            ants = node.nodeset("&ant")
            ptree = build_ptree(ants, self.all_vars)
            for cq in node.nodeset("cq"):
                chsub = restrict_binding_to_pat(subst, cq)
                ch = Channel(subst, chsub, ct, cq, OPEN)
                cqch = Cqch(ch, ants, [ptree, ptree_to_adj_list(ptree), []])
                f.RULE_USE_CHANNELS = cqchset_insert(cqch, f.RULE_USE_CHANNELS)
                self.send_ant_requests_rule(f, cqch)
        else:
            cqs = (self.consequents(node, signature) if self.is_ant_to_rule_rep(report, node)
                   else self.all_consequents(node))
            for cq in cqs:
                ants = self.antecedents(node, cq)
                chsub = restrict_binding_to_pat(subst, cq)
                ch = Channel(subst, chsub, ct, cq, OPEN)
                rui = RUI(chsub, 0, 0, nodeset_to_fnodeset(ants), False)
                f.RULE_USE_CHANNELS = cqchset_insert(Cqch(ch, ants, [rui]), f.RULE_USE_CHANNELS)
                if not (f.TYPE in ("or-entailment", "when-do", "whenever-do")
                        and self.is_ant_to_rule_rep(report, node)):
                    self.broadcast_ant_request(f, ch, tuple(a for a in ants if a is not signature),
                                               ch.filter, subst)

    # ------------------------------------------------------------------
    # rule introduction (rule-bintr, rule-eintr)
    def is_case_of_introduction(self, f: Frame, ch: Channel) -> bool:
        return (getattr(f, "NAME", None) == "rule"
                and f.TYPE in ("and", "nor", "or-entailment", "and-entailment")
                and (self.is_from_user_req(ch) or self.is_rule_to_ant_req(ch, f.NODE)
                     or self.is_rule_to_cq_req(ch, f.NODE)))

    def not_working_on_introduction(self, f: Frame, restr: Any, ct: Any) -> bool:
        for ich in f.INTRODUCTION_CHANNELS:
            ch = ich.channel
            if restr_equivalent(restr, ch.filter) and self.issubset_ctx(ct, ch.context):
                return False
        return True

    def initiate_introduction_rule(self, f: Frame, ch: Channel) -> Any:
        if f.NODE.quantified_vars():
            return None
        t = f.TYPE
        if t == "or-entailment":
            return self._initiate_vent_introduction(f, ch)
        if t == "and-entailment":
            return self._initiate_and_ent_introduction(f, ch)
        if t in ("and", "nor"):
            return self._initiate_introduction_without_hypothesis(f, ch)
        return None

    def _initiate_and_ent_introduction(self, f: Frame, ch: Channel) -> Any:
        node = f.NODE
        subst_ants: tuple = ()
        for ant in self.antecedents(node, None):
            sa = self.applysubst(ant, ch.filter)
            if sa.is_mol:
                subst_ants = ns_insert(sa, subst_ants)
            else:
                return None
        aants = self._assert_all_ants(subst_ants)
        cqts = self.consequents_ent(node)
        extended_ct: Any = self.fullbuildcontext(aants, (self.ctx(ch.context),))
        ich = self.install_introduction_channel(f, ch, aants, cqts)
        restr = ch.filter
        if self.use_intensional_contexts:
            name = self.gentemp("C-&=>-INTRO-")
            self.name_ct(extended_ct, name)
            extended_ct = name
        if aants:
            self.remark("\nLet me assume that", (aants[0],), restr)
        for aant in aants[1:]:
            self.remark("and  assume  that ", (aant,), restr)
        return self.send_cq_requests_rule(f, ich, extended_ct)

    def _initiate_vent_introduction(self, f: Frame, ch: Channel) -> None:
        node = f.NODE
        ants = self.antecedents(node, None)
        cqts = self.consequents_ent(node)
        restr = ch.filter
        if len(ants) != 1:
            return
        for ant in ants:
            sa = self.applysubst(ant, ch.filter)
            if sa.is_mol:
                ct = self.getcontext(())
                crntct = self.gentemp("CvANT")
                self.name_ct(ct, crntct)
                with self.let(crntct=crntct):
                    self.assert_n(sa)
                    aant = sa
                    ich = self.install_introduction_channel(f, ch, (aant,), cqts)
                    extended_ct: Any = self.fullbuildcontext((aant,), (self.ctx(ch.context),))
                    if self.use_intensional_contexts:
                        name = self.gentemp("C-v=>-INTRO-")
                        self.name_ct(extended_ct, name)
                        extended_ct = name
                    self.remark("\nLet me assume that", (aant,), restr)
                    self.send_cq_requests_rule(f, ich, extended_ct)

    def _initiate_introduction_without_hypothesis(self, f: Frame, ch: Channel) -> Any:
        cqts = self.all_consequents(f.NODE)
        ich = self.install_introduction_channel(f, ch, (), cqts)
        return self.send_cq_requests_rule(f, ich, ch.context)

    def _assert_all_ants(self, ants: tuple) -> tuple:
        ct = self.getcontext(())
        crntct = self.gentemp("C&ANT")
        self.name_ct(ct, crntct)
        with self.let(crntct=crntct):
            for ant in ants:
                self.assert_n(ant)
        return ants

    def send_cq_requests_rule(self, f: Frame, ich: Ich, extended_ct: Any) -> bool:
        ch = ich.channel
        cqts = ich.consequents
        f.INTRODUCTION_CHANNELS = ichset_update(Ich(ch, ich.context, cqts,
                                                    request_all(ich.ruiset)),
                                                f.INTRODUCTION_CHANNELS)
        for n in cqts:
            self.send_introduction_request(
                Channel(restrict_binding_to_pat(ch.filter, n), (), extended_ct, f.NODE, OPEN), n)
        return True

    def send_introduction_request(self, req: Channel, n: Node) -> None:
        self.activate_n(n)
        pr = self.activation_n(n)
        pr.slots["REQUESTS"] = chset_insert(req, pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        self.initiate(pr)

    def install_introduction_channel(self, f: Frame, request: Channel, ants: tuple,
                                     cqts: tuple) -> Ich:
        dest = request.destination
        # (unless (is-from-user.req request) (restrict ...) (filter.ch request)):
        # the filter itself when the request is not from the user, else nil.
        destsub = () if self.is_from_user_req(request) else request.filter
        ich = Ich(Channel(destsub, request.switch, request.context, dest, request.valve),
                  ants, cqts, [RUI(destsub, 0, 0, nodeset_to_fnodeset(cqts), False)])
        f.INTRODUCTION_CHANNELS = ichset_insert(ich, f.INTRODUCTION_CHANNELS)
        if not self.is_from_user_req(request):
            self.activate_n(dest)
        return ich

    def process_one_introduction_report_rule(self, f: Frame, report: Report) -> Any:
        anysent = None
        for ich in list(f.INTRODUCTION_CHANNELS):
            anysent = self._try_to_send_introduction_conclusion(f, report, ich) or anysent
        return anysent

    def _try_to_send_introduction_conclusion(self, f: Frame, report: Report, ich: Ich) -> Any:
        ch = ich.channel
        if not compatible(report.subst, ch.filter):
            return None
        if f.TYPE in ("and", "nor"):
            fs = self.filter_sup(report.support, ch.context)
        else:
            fs = self._filter_introduction_support(report.support, ich.context, ch.context)
        if fs:
            return self.introduction_end_handler(
                f, Report(report.subst, fs, report.sign, report.signature, report.node,
                          report.context), ich)
        return None

    def _filter_introduction_support(self, support: tuple, extra_hyps: tuple,
                                     ct_channel: Any) -> tuple:
        new: tuple = ()
        c = self.ctx(ct_channel)
        ch_hyps = c.hyps if c is not None else ()
        for ct in ctcs_get("der", support):
            if _ns_equal(extra_hyps, ns_compl(ct.hyps, ns_compl(ch_hyps, extra_hyps))):
                new = ctcs_insert("der", self.fullbuildcontext(ns_compl(ct.hyps, extra_hyps)),
                                  new)
        return new

    def introduction_end_handler(self, f: Frame, intr_report: Report, ich: Ich) -> bool:
        node = f.NODE
        ch = ich.channel
        cqs = ich.consequents
        updated_ruiset = ich.ruiset
        dest = ch.destination
        crntct = ch.context
        for rui in self._get_introduction_info(intr_report, ich):
            def subst_of(rui: RUI) -> tuple:
                if isinstance(dest, Node):
                    return sbst_restrict(rui.subst, self.all_vars(dest))
                return rui.subst
            if f.TYPE == "and" and rui.poscount == 0 and rui.negcount == 1:
                restr = rui.subst
                rep = Report(subst_of(rui), self._compute_new_support_intr(f, rui.fns), NEG,
                             node, None, crntct)
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nSince it is not the case that", (intr_report.signature,),
                                restr)
                    self.remark("I infer it is not the case that", (node,), restr)
                self.send_reports([rep], ch)
            if f.TYPE == "nor" and rui.poscount == 1 and rui.negcount == 0:
                restr = rui.subst
                rep = Report(subst_of(rui), self._compute_new_support_intr(f, rui.fns), NEG,
                             node, None, crntct)
                if not rui.remarkedp:
                    rui = rui._replace(remarkedp=True)
                    self.remark("\nSince it is the case that", (intr_report.signature,), restr)
                    self.remark("I infer it is not the case that", (node,), restr)
                self.send_reports([rep], ch)
            count = rui.negcount if f.TYPE == "nor" else rui.poscount
            if count == len(cqs):
                aants = ich.context
                restr = rui.subst
                rep = Report(subst_of(rui), self._compute_new_support_intr(f, rui.fns), POS,
                             node, None, crntct)
                self._inform_introduction(f, restr, aants, cqs)
                self.send_reports([rep], ch)
                self._try_to_use_introduction_conclusion(f, rep)
            updated_ruiset = ruis_update(rui, updated_ruiset)
            f.INTRODUCTION_CHANNELS = ichset_update(Ich(ch, ich.context, cqs, updated_ruiset),
                                                    f.INTRODUCTION_CHANNELS)
        return True

    def _try_to_use_introduction_conclusion(self, f: Frame, report: Report) -> None:
        instance = Instance(report.subst, report.support, report.sign)
        if not instance.subst:
            self.broadcast_one_report(f, report)
            self.try_applying_one_report(f, report)
        elif self.unknown_inst(f, instance):
            node = f.NODE
            if node.quantified_vars():
                newnode = self.find_or_build(self.clean_quantifiers_cs(
                    self.apply_subst_cs(report.subst, self.n_to_downcs(node))))[0]
            else:
                newnode = self.applysubst(node, report.subst)
            self.added_nodes = ns_insert(newnode, self.added_nodes)
            f.KNOWN_INSTANCES = iset_insert(instance, f.KNOWN_INSTANCES)
            self.broadcast_one_report(f, report)
            self.try_applying_one_report(f, report)

    def _get_introduction_info(self, report: Report, ich: Ich) -> list:
        sbst, cq, supp = report.subst, report.signature, report.support
        result: list = []
        for rui in ich.ruiset:
            flag = fns_flag(cq, rui.fns)
            if sbst_is_compatible(sbst, rui.subst):
                if not rui.fns or flag in (UNKNOWN, REQUESTED):
                    result = ruis_update(rui_update(RUI(sbst_union(rui.subst, sbst), rui.poscount,
                                                        rui.negcount, rui.fns, rui.remarkedp),
                                                    cq, supp, report.sign), result)
                elif flag in (TRUE, FALSE) and self.filter_sup(fns_support(cq, rui.fns),
                                                               report.context):
                    result = ruis_update(RUI(rui.subst, rui.poscount, rui.negcount,
                                             fns_update(rui.fns, cq, supp, flag), rui.remarkedp),
                                         result)
        return result

    def _inform_introduction(self, f: Frame, restr: Any, aants: tuple, cqs: tuple) -> None:
        node = f.NODE
        if f.TYPE == "and":
            self.remark("\nSince", (cqs[0],), restr)
            for cq in cqs[1:]:
                self.remark("and ", (cq,), restr)
            self.remark("I infer", (node,), restr)
        elif f.TYPE == "nor":
            self.remark("\nSince it is not the case that", (cqs[0],), restr)
            for cq in cqs[1:]:
                self.remark("and since not", (cq,), restr)
            self.remark("I infer", (node,), restr)
        else:
            self.remark("\nSince", (cqs[0],), restr)
            for cq in cqs[1:]:
                self.remark("and", (cq,), restr)
            self.remark("was derived assuming" if len(cqs) == 1 else "were derived assuming",
                        (aants[0],) if aants else (), restr)
            for ant in aants[1:]:
                self.remark("and assuming", (ant,), restr)
            self.remark("I infer", (node,), restr)

    def _compute_new_support_intr(self, f: Frame, fns: tuple) -> tuple:
        new: tuple = ()
        suplist = fns_to_suplist(fns)
        if len(suplist) <= 1:
            combos = sup_to_combinations(suplist[0] if suplist else ())
        else:
            combos = combinations_of(suplist[0], suplist[1:])
        for i in range(0, len(combos), 2):
            ots, cts = combos[i], combos[i + 1]
            ot = (combine_and_intr_ots_star(ots, cts) if f.TYPE == "and"
                  else combine_ots_star(ots))
            new = ctcs_insert(ot, self.fullbuildcontext((), cts), new)
        return new

    # ------------------------------------------------------------------
    # user processes (user, deducetrue, with-acts)
    def _tally(self, f: Frame, report: Report) -> None:
        if report.sign == POS:
            f.POS_FOUND += 1
        else:
            f.NEG_FOUND += 1

    @staticmethod
    def _enough_answers(f: Frame) -> bool:
        if f.TOTAL_DESIRED is None and f.POS_DESIRED is None:
            return False
        if isinstance(f.TOTAL_DESIRED, int):
            return not (f.POS_FOUND + f.NEG_FOUND < f.TOTAL_DESIRED)
        return not (f.POS_FOUND < f.POS_DESIRED or f.NEG_FOUND < f.NEG_DESIRED)

    def _user_common(self, f: Frame, accept: Any) -> None:
        reports = f.REPORTS
        f.REPORTS = []
        for report in reports:
            n = report.node
            if not ns_ismemb(n, f.DEDUCED_NODES) and accept(report):
                self._tally(f, report)
                f.DEDUCED_NODES = ns_insert(n, f.DEDUCED_NODES)
        self.deduction_results = ns_union(f.DEDUCED_NODES, tuple(self.deduction_results or ()))
        if f.CLIENT != USER:
            self._send_to_client(f.CLIENT, f.DEDUCED_NODES)
        if self._enough_answers(f):
            self.clear_all_queues()
        self.write_back(f)

    def p_user(self, f: Frame) -> None:
        self._user_common(f, lambda r: True)

    def p_posuser(self, f: Frame) -> None:
        self._user_common(f, lambda r: r.sign == POS)

    def p_neguser(self, f: Frame) -> None:
        self._user_common(f, lambda r: r.sign == NEG)

    def _wh_common(self, f: Frame, sign: str) -> None:
        reports = f.REPORTS
        f.REPORTS = []
        for report in reports:
            n = report.node
            if any(_cdr_is(entry, n) for entry in f.DEDUCED_NODES) or report.sign != sign:
                continue
            self._tally(f, report)
            entry = tuple(((v.snepslog or v), self.applysubst(v, report.subst)) for v in f.VARS)
            if not any(_entry_equal(entry, e) for e in f.DEDUCED_NODES):
                f.DEDUCED_NODES = [entry] + list(f.DEDUCED_NODES)
        self.deduction_results = list(f.DEDUCED_NODES) + list(self.deduction_results or ())
        if f.CLIENT != USER:
            self._send_to_client(f.CLIENT, f.DEDUCED_NODES)
        if self._enough_answers(f):
            self.clear_all_queues()
        self.write_back(f)

    def p_whuser(self, f: Frame) -> None:
        self._wh_common(f, POS)

    def p_notwhuser(self, f: Frame) -> None:
        self._wh_common(f, NEG)

    def _send_to_client(self, client: Process, deduced: Iterable) -> None:
        prior = client.slots["REPORTS"]
        for d in deduced:
            prior = ns_insert(d, prior) if isinstance(d, Node) else prior
        client.slots["REPORTS"] = prior

    # ------------------------------------------------------------------
    # deduce and add (deduce, deducetrue, add, dynamic-add)
    def _new_user(self, kind: str, how_many: Any, target: Optional[Node] = None) -> Process:
        total = how_many if isinstance(how_many, int) else None
        posd = how_many[0] if isinstance(how_many, (list, tuple)) else None
        negd = how_many[1] if isinstance(how_many, (list, tuple)) else None
        if kind in ("whuser", "notwhuser"):
            return Process(kind, target.freevars, [], self.crntct, [], total, posd, negd, 0, 0,
                           USER, HIGH)
        return Process(kind, [], self.crntct, (), total, posd, negd, 0, 0, USER, HIGH)

    def _deduce(self, kind: str, how_many: Any, targetset: tuple) -> Any:
        inference_context = self.crntct if self.use_intensional_contexts \
            else self.value_sv(self.crntct)
        self.added_nodes = ()
        self.deduction_results = [] if kind in ("whuser", "notwhuser") else ()
        if not targetset:
            return self.deduction_results
        target = targetset[0]
        self.user_process = self._new_user(kind, how_many, target)
        self.activate_n(target)
        pr = self.activation_n(target)
        pr.slots["REQUESTS"] = chset_insert(Channel((), (), inference_context, USER, OPEN),
                                            pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        self.multip(deque(), deque([pr]), deque())
        return self.deduction_results

    def deduce_star(self, how_many: Any, targetset: tuple) -> tuple:
        return self._deduce("user", how_many, targetset)

    def deducetrue_star(self, how_many: Any, targetset: tuple) -> tuple:
        return self._deduce("posuser", how_many, targetset)

    def deducefalse_star(self, how_many: Any, targetset: tuple) -> tuple:
        return self._deduce("neguser", how_many, targetset)

    def deducewh_star(self, how_many: Any, targetset: tuple) -> list:
        return self._deduce("whuser", how_many, targetset)

    def deducewhnot_star(self, how_many: Any, targetset: tuple) -> list:
        return self._deduce("notwhuser", how_many, targetset)

    def add_star(self, new_nodes: tuple) -> tuple:
        inference_context = self.crntct if self.use_intensional_contexts \
            else self.value_sv(self.crntct)
        self.added_nodes = new_nodes
        if new_nodes:
            queue: deque = deque()
            for n in new_nodes:
                if n.is_mol:
                    self.activate_n(n)
                    pr = self.activation_n(n)
                    pr.slots["REPORTS"] = repset_insert(
                        Report((), self.filter_sup(n.asupport, self.crntct), POS, USER, n,
                               inference_context), pr.slots["REPORTS"])
                    pr.slots["PRIORITY"] = HIGH
                    queue.append(pr)
            self.multip(deque(), queue, deque())
        return self.added_nodes

    def dynamic_add_star(self, new_nodes: tuple) -> tuple:
        inference_context = self.crntct if self.use_intensional_contexts \
            else self.value_sv(self.crntct)
        self.added_nodes = new_nodes
        if new_nodes and new_nodes[0].is_mol:
            n = new_nodes[0]
            self.activate_n(n)
            pr = self.activation_n(n)
            pr.slots["REPORTS"] = repset_insert(
                Report((), self.filter_sup(n.asupport, self.crntct), POS, SENSOR, n,
                       inference_context), pr.slots["REPORTS"])
            pr.slots["PRIORITY"] = HIGH
            self.initiate(pr)
        return self.added_nodes

    # ------------------------------------------------------------------
    # tracing (remark)
    def surface_trace_p(self) -> bool:
        it = self.infertrace
        return self.snepslog_running or (isinstance(it, str) and it.lower() == "surface")

    def remark(self, msg: str, nodeset: Any, restriction: Any, context: Any = None,
               fresh: bool = False) -> None:
        it = self.infertrace
        if not it:
            return
        if callable(it):
            it(self, msg, nodeset, restriction)
            return
        if fresh:
            self.fresh_line()
        if self.surface_trace_p():
            self.write(msg)
            nodes = [self.applysubst(n, _restr_subst(restriction)) for n in (nodeset or ())]
            self.surface(nodes)
            if context is not None:
                self.remark_context(context)
        else:
            self.write(msg)
            self.pp_nodetree(self.describe_nodeset(nodeset, restriction))
            if context is not None:
                self.remark_context(context)

    def surface(self, nodes: Iterable[Node]) -> None:
        """Print NODES for an inference trace; SNePSLOG prints them as wffs."""
        self.describe_nodes(nodes, full=True)

    def remark_context(self, context: Any) -> None:
        c = self.ctx(context)
        if c is None:
            return
        names = list(c.names)
        if not names:
            self.write("holds within the BS defined by hypotheses "
                       + self.slight_describe_or_surface_ns(c.hyps) + " \n")
        else:
            s = "s" if len(names) != 1 else ""
            rest = "".join(f", {x}" for x in names[1:])
            self.write(f"holds within the BS defined by context{s} {names[0]}{rest} \n")

    def slight_describe_or_surface_ns(self, nodeset: Iterable[Node]) -> str:
        descrs = [str(self.slight_describe_or_surface(n)) for n in nodeset]
        if not descrs:
            return "(nil)"
        return "(" + descrs[0] + "".join(" " + d for d in descrs[1:]) + ")"

    def describe_nodeset(self, nodeset: Any, restriction: Any) -> list:
        return [self.describe_one_node(n, restriction) for n in (nodeset or ())]

    def describe_one_node(self, node: Any, restriction: Any) -> Any:
        sbst = _restr_subst(restriction)
        if not isinstance(node, Node):
            return node
        if node.is_base:
            if node.is_number():
                return node.to_number()
            return [node]
        if node.is_var:
            t = sbst_binding(node, sbst)
            if t is not None:
                return [node, "<--", t]
            return node
        return [node] + [[r] + [self.describe_one_node(n, restriction) for n in ns]
                         for r, ns in self.n_to_downcs(node)]

    PROCESS_FUNCTIONS = {
        "non-rule": lambda self, f: self.p_non_rule(f),
        "rule": lambda self, f: self.p_rule(f),
        "num-quant.rule": lambda self, f: self.p_rule(f),
        "user": lambda self, f: self.p_user(f),
        "posuser": lambda self, f: self.p_posuser(f),
        "neguser": lambda self, f: self.p_neguser(f),
        "whuser": lambda self, f: self.p_whuser(f),
        "notwhuser": lambda self, f: self.p_notwhuser(f),
        "act": lambda self, f: self.p_act(f),
    }


def _cdr_is(entry: Any, n: Any) -> bool:
    # (member n *DEDUCED-NODES* :key #'cdr): the cdr of an entry is a list,
    # never a node, so this test never succeeds -- kept for fidelity.
    return False


def _entry_equal(a: tuple, b: tuple) -> bool:
    return len(a) == len(b) and all(x[0] == y[0] and x[1] is y[1] for x, y in zip(a, b))


def _ns_equal(a: Any, b: Any) -> bool:
    a, b = tuple(a or ()), tuple(b or ())
    return len(a) == len(b) and all(x is y for x, y in zip(a, b))


def _max_height_sub(sub: Iterable) -> int:
    m = 0
    for _v, term in sub or ():
        if isinstance(term, Node):
            m = max(m, term.height)
    return m


def _sstr(sub: Iterable) -> str:
    return " ".join(f"({v} . {t})" for v, t in sub or ())


def _nor_to_nor_with_different_args(n1: Any, n2: Any) -> bool:
    return (isinstance(n1, Node) and isinstance(n2, Node) and n1.is_nor() and n2.is_nor()
            and len(n1.nodeset("arg")) != len(n2.nodeset("arg")))


def _fill_out_report_substs(repset: list, sbst: Iterable) -> list:
    return [Report(sbst_union(sbst, r.subst), r.support, r.sign, r.signature, r.node, r.context)
            for r in repset]


def _get_updated_cqch(cqch: Cqch, cqchs: list) -> Optional[Cqch]:
    result = None
    for c in cqchs:
        if ch_equivalent(cqch.channel, c.channel):
            result = c
    return result
