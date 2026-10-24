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
"""SNeBR, the SNePS belief revision system (``snebr/``).

When a newly asserted or derived proposition contradicts a believed one,
SNeBR records the inconsistent hypothesis sets (nogoods) and either asks
the user how to revise the context (reading the answers from the input
stream, as SNePS does) or, in automatic mode, removes the least entrenched
culprit hypotheses using the current epistemic-entrenchment order.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional

from ..core.context import Context
from ..core.node import Node
from ..core.nodeset import (ctcs_insert, ctcs_to_cts, ctcs_to_ots, ns_compl, ns_insert,
                            ns_intersect, ns_ismemb, ns_issubset, ns_member, ns_remove, ns_union)
from ..io.streams import NullOutputStream
from ..snip.multi import StopInference
from ..snip.structs import combine_ots_star

OrderFn = Callable[[Any, Node, Node], bool]


def null_order(net: Any, lhs: Node, rhs: Node) -> bool:
    return True


class BRMixin:
    def _init_snebr(self) -> None:
        self.br_auto_mode = False
        self.br_tie_mode = False
        self.br_totalorder: OrderFn = null_order
        self.order_cache: list = []
        self.order_cache_complement: list = []
        self.crntctname: Any = None
        self.br_answer: Optional[Callable[[str], Any]] = None
        self._br_depth = 0

    # ------------------------------------------------------------------
    # detection (contrad)
    def ck_contradiction(self, newnode: Node, context: Any, flag: str) -> Node:
        for contr in self.contradictory_nodes(newnode):
            if contr is not None and self._exists_contradiction(contr, context):
                self._ck_contradiction_1(newnode, contr, context, flag)
        return newnode

    def _exists_contradiction(self, contr: Node, context: Any) -> bool:
        with self.let(crntct=context):
            return self.isassert(contr)

    def _ck_contradiction_1(self, newnode: Node, contr: Node, context: Any, flag: str) -> None:
        contrsup = ctcs_to_cts(contr.asupport)
        self.update_contexts(ctcs_to_cts(newnode.asupport), contrsup)
        ct = self.ctx(context)
        if ct is not None:
            ct.kinconsistent = True
        both = self.isassert(newnode) and self.isassert(contr)
        if both and not (ct is not None and ct.okinconsistent):
            if flag == "assertion":
                self.sneps_contr_handler(newnode, contr)
            else:
                self.snip_contr_handler(newnode, contr, context)
        if self.isassert(newnode) and self.isassert(contr):
            self.ok_update_contexts(ctcs_to_cts(newnode.asupport), contrsup)
            ct = self.ctx(context)
            if ct is not None:
                ct.okinconsistent = True

    def ck_inconsistency(self, newct: Context) -> bool:
        if self.isinconsis_ct(newct):
            self.write(f"\n\n The context {_plist(newct.hyps)}\n"
                       "  that you are trying to build is inconsistent.")
            self.write("\n\n\n You have the following options:"
                       "\n  1. [y]es, create the context anyway, knowing that a contradiction "
                       "is derivable;"
                       "\n  2. [n]o,don't create the context."
                       "\n (please type y or n)")
            return not self._user_says_yes()
        return False

    # ------------------------------------------------------------------
    # interaction
    def _br_read(self) -> Any:
        """Read one answer from the input stream: a number, a (lower-case)
        word, or None at the end of the input."""
        self.write("\n=><= ")
        if self.br_answer is not None:
            return self.br_answer("")
        if self.inunit is None:
            return None
        from ..snepsul.reader import EOF, ReaderError, SnepsulReader
        try:
            obj = SnepsulReader(self.inunit, fold_case="lower", macros=False).read()
        except ReaderError:
            return ""
        return None if obj is EOF else obj

    @staticmethod
    def _ans_is(ans: Any, option: str) -> bool:
        return isinstance(ans, str) and ans.lower() == option.lower()

    def _read_option(self, options: str, retry_msg: str, numbers: tuple = ()) -> Any:
        tries = 0
        while True:
            ans = self._br_read()
            if ans is None:
                return options[0]
            if isinstance(ans, int) and ans in numbers:
                return ans
            for o in options:
                if self._ans_is(ans, o):
                    return o
            self.write(retry_msg)
            tries += 1
            if tries > 100:
                return options[0]

    def _user_says_yes(self) -> bool:
        while True:
            ans = self._br_read()
            if ans is None:
                return False
            name = ans if isinstance(ans, str) else ""
            if name.lower() in ("y", "yes", "ok", "sure"):
                return True
            if name.lower() in ("n", "no"):
                return False
            self.write("Please type n or y")

    def describe_or_surface(self, node: Node) -> str:
        from ..core.printing import pretty_text
        if self.surface_trace_p():
            return self.surface_string(node)
        return pretty_text(self.describe_one_node(node, None), escape=False, column=0)

    def surface_string(self, node: Node) -> str:
        return str(node)

    # ------------------------------------------------------------------
    # assertion contradictions (snepshandler)
    def sneps_contr_handler(self, newnode: Node, contrnd: Node) -> None:
        if self.br_auto_mode:
            self._implement_sneps_option("a", newnode, contrnd)
            return
        self.write(f"\n\n A contradiction was detected within context {self.crntct}."
                   "\n The contradiction involves the proposition you want to assert:"
                   f"\n   {self.describe_or_surface(newnode)} "
                   "\n and the previously existing proposition:"
                   f"\n   {self.describe_or_surface(contrnd)}")
        self.write("\n\n\n You have the following options:"
                   "\n  1. [a] to attempt to resolve the contradiction automatically "
                   "\n  2. [c] to continue anyway, knowing that a contradiction is derivable;"
                   "\n  3. [r] to revise the inconsistent part of the context manually"
                   "\n  4. [d] to discard this contradictory new assertion from the context"
                   "\n (please type a, c, r or d)")
        opt = self._read_option("acrd", "Please type a, c, r or d")
        self._implement_sneps_option(opt, newnode, contrnd)

    def _implement_sneps_option(self, option: str, newnode: Node, contrnd: Node) -> None:
        crntct = self.crntct
        if option == "d":
            ct = self.get_context(crntct)
            self.name_ct(self.buildcontext(ns_remove(newnode, ct.hyps)), crntct)
        elif option == "a":
            contrsup = ctcs_to_cts(contrnd.asupport)
            newsup = ctcs_to_cts(newnode.asupport)
            self.autobr(newsup, contrsup, self.get_context(crntct), False)
            self.clear_infer()
            self._rerun_command()
        elif option == "r":
            contrsup = ctcs_to_cts(contrnd.asupport)
            contr_ots = ctcs_to_ots(contrnd.asupport)
            newsup = ctcs_to_cts(newnode.asupport)
            new_ots = ctcs_to_ots(newnode.asupport)
            self.clear_infer()
            self.change_context(newsup, contrsup, new_ots, contr_ots, self.get_context(crntct),
                                crntct)
            self._rerun_command()
        elif option == "c":
            self.get_context(crntct).okinconsistent = True

    def _rerun_command(self, command: Any = None) -> Any:
        if command is None:
            command = self.value_sv("command")
        if command is None or self._br_depth > 20:
            return None
        self._br_depth += 1
        try:
            return self.topsneval(command)
        finally:
            self._br_depth -= 1

    def remove_hyps_silently(self, hyps: Iterable[Node], ctname: Any) -> Any:
        """Remove HYPS from the context CTNAME as a top-level command with its
        output suppressed (so it becomes the command that is re-run after a
        revision, as in SNePS)."""
        hyps = tuple(hyps)
        with self.let(outunit=NullOutputStream()):
            return self.topsneval(lambda: self.remove_from_context(hyps, ctname))

    def topsneval(self, command: Any) -> Any:
        """Run a command; the SNePSUL layer also evaluates SNePSUL forms."""
        if callable(command):
            return command()
        return None

    # ------------------------------------------------------------------
    # automatic belief revision
    def autobr(self, newnd_supps: Iterable[Context], contrnd_supps: Iterable[Context],
               context: Any, forward_inference_flag: bool = True,
               assert_negation_flag: bool = True) -> Any:
        ctx = self.ctx(context)
        chyps = ctx.hyps if ctx is not None else ()
        contrnd_supps = list(contrnd_supps or ())
        hyp_sets: list = []
        for newsupp in newnd_supps or ():
            if not contrnd_supps:
                u = newsupp.hyps
                if ns_issubset(u, chyps):
                    hyp_sets.insert(0, u)
            else:
                for contrsupp in contrnd_supps:
                    u = ns_union(newsupp.hyps, contrsupp.hyps)
                    if ns_issubset(u, chyps):
                        hyp_sets.insert(0, u)
        culprits = self.get_culprits(hyp_sets)
        self.remark("\nAutomatic Belief Revision disbelieving", culprits, None)
        self.remove_hyps_silently(culprits, self.crntct)
        if not forward_inference_flag:
            self.clear_infer()
        if assert_negation_flag:
            for culprit in culprits:
                neg = self.negate_n(culprit)
                others = [c for c in culprits if c is not culprit]
                for hs in hyp_sets:
                    if (ns_member(culprit, hs) and not ns_intersect(tuple(others), hs)
                            and not ns_member(neg, hs)):
                        support_ct = self.buildcontext(ns_remove(culprit, hs))
                        neg.asupport = ctcs_insert("ext", support_ct, neg.asupport)
                self.add_star((neg,))
        self.most_entrenched_props = ()
        return self.crntct

    def _auto_order(self, comp: OrderFn) -> Callable[[Node, Node], bool]:
        def order(lhs: Node, rhs: Node) -> bool:
            mep = self.most_entrenched_props or ()
            return ns_member(rhs, mep) or (not ns_member(lhs, mep) and bool(comp(self, lhs, rhs)))
        return order

    @staticmethod
    def _lex_order_lt(comp: Callable[[Node, Node], bool]) -> Callable[[Node, Node], bool]:
        def order(lhs: Node, rhs: Node) -> bool:
            fwd = comp(lhs, rhs)
            if fwd and comp(rhs, lhs):
                return str(lhs) < str(rhs)
            return fwd
        return order

    def _order_cache_le(self, lhs: Node, rhs: Node, order: Callable[[Node, Node], bool]) -> bool:
        key = (lhs, rhs)
        if any(k[0] is lhs and k[1] is rhs for k in self.order_cache):
            return True
        if any(k[0] is lhs and k[1] is rhs for k in self.order_cache_complement):
            return False
        if order(lhs, rhs):
            self.order_cache.insert(0, key)
            return True
        self.order_cache_complement.insert(0, key)
        return False

    def get_culprits(self, no_goods: list) -> list:
        self.order_cache = []
        self.order_cache_complement = []
        order_le = self._auto_order(self.br_totalorder)
        order_lt = self._lex_order_lt(self._auto_order(self.br_totalorder))

        def cached_lt(l: Node, r: Node) -> bool:
            return self._order_cache_le(l, r, order_lt)

        def cached_gt(l: Node, r: Node) -> bool:
            return not self._order_cache_le(l, r, order_lt)
        if not self.br_tie_mode:
            return self._assist_get_culprits([list(ng) for ng in no_goods], order_le)
        sno: list = []
        for ng in no_goods:
            sno.insert(0, _min_to_front(list(ng), cached_lt))
        sno = _merge_sort(sno, lambda a, b: cached_gt(a[0], b[0]))
        culprits: list = []
        while sno:
            current = sno[0][0]
            culprits.insert(0, current)
            for ng in list(sno):
                if any(x is current for x in ng):
                    sno = [x for x in sno if x != ng]
        return culprits

    def _assist_get_culprits(self, no_goods: list, order_le: Callable[[Node, Node], bool]) -> list:
        culprits: list = []
        for _round in range(10000):
            possible_mins: list = []
            for ng in no_goods:
                mins: list = []
                for lhs in ng:
                    if all(self._order_cache_le(lhs, rhs, order_le) for rhs in ng):
                        mins.insert(0, lhs)
                possible_mins.append(mins)
            while True:
                done = True
                i = 0
                # (do* ((i 0 (+ i 1)) (group (nth i possible-mins) ...)) ((null group)) ...):
                # the scan continues over the shrinking lists after a removal.
                while i < len(possible_mins) and possible_mins[i]:
                    group = possible_mins[i]
                    ng = no_goods[i] if i < len(no_goods) else []
                    if len(group) == 1:
                        cand = group[0]
                        rest_mins = [x for x in ng if x is not cand]
                        other_mins: list = []
                        for og in possible_mins:
                            if og is group:
                                continue
                            for x in og:
                                if not any(x is y for y in other_mins):
                                    other_mins.append(x)
                        if not any(any(x is y for y in rest_mins) for x in other_mins):
                            done = False
                            culprits.insert(0, cand)
                            possible_mins = [g for g in possible_mins
                                             if not any(x is cand for x in g)]
                            no_goods = [g for g in no_goods if not any(x is cand for x in g)]
                            if not no_goods:
                                return culprits
                    i += 1
                if done:
                    break
            # ask the user to break the first tie
            for group in possible_mins + [[]]:
                if len(group) != 1:
                    if not group:
                        return culprits
                    chosen = self._assist_choose_min(group)
                    for rest in [x for x in group if x is not chosen]:
                        if self._order_cache_le(rest, chosen, order_le):
                            self.order_cache = [k for k in self.order_cache
                                                if not (k[0] is rest and k[1] is chosen)]
                            self.order_cache_complement.insert(0, (rest, chosen))
                    break
        return culprits

    def _assist_choose_min(self, mins: list) -> Node:
        if len(mins) == 1:
            return mins[0]
        self.write("\n Please choose from the following hypotheses the one that you would "
                   "\n least like to keep:\n")
        self._print_num_lst(mins, mins)
        ans = self._br_read()
        if isinstance(ans, int) and 1 <= ans <= len(mins):
            return mins[ans - 1]
        return mins[0]

    # ------------------------------------------------------------------
    # derived contradictions (sniphandler)
    def snip_contr_handler(self, newnode: Node, contrnd: Node, context: Any) -> None:
        if not self.br_auto_mode:
            self.write(f"\n\n A contradiction was detected within context {self.crntctname}."
                       "\n The contradiction involves the newly derived proposition:"
                       f"\n   {self.describe_or_surface(newnode)} "
                       "\n and the previously existing proposition:"
                       f"\n   {self.describe_or_surface(contrnd)}")
        self._contr_h(ctcs_to_cts(newnode.asupport), ctcs_to_cts(contrnd.asupport),
                      ctcs_to_ots(newnode.asupport), ctcs_to_ots(contrnd.asupport), context)

    def _contr_h(self, newnd_supps: tuple, contrnd_supps: tuple, newnd_ots: list,
                 contrnd_ots: list, context: Any) -> None:
        if not self.br_auto_mode:
            self.write("\n You have the following options:"
                       "\n  1. [A]ttempt to resolve the contradiction automatically;"
                       "\n  2. [C]ontinue anyway, knowing that a contradiction is derivable;"
                       "\n  3. [R]e-start the exact same run in a different context which is"
                       "\n     not inconsistent;"
                       "\n  4. [D]rop the run altogether.\n"
                       "\n (please type a, c, r or d)")
            ans = self._read_option("acrd", "Please type a, c, r or d", (1, 2, 3, 4))
            ans = {1: "a", 2: "c", 3: "r", 4: "d"}.get(ans, ans)
        else:
            ans = "a"
        lastcommand = self.value_sv("command")
        mep = self.most_entrenched_props
        if ans == "c":
            return
        if ans == "a":
            self.autobr(newnd_supps, contrnd_supps, context)
            cur = self.get_context(self.crntct)
            if newnd_supps and cur is not None and ns_issubset(newnd_supps[0].hyps, cur.hyps):
                self.most_entrenched_props = mep
                self._rerun_command(lastcommand)
                return
            raise StopInference
        self.clear_all_queues()
        self.clear_infer()
        if ans == "r":
            self.change_context(newnd_supps, contrnd_supps, newnd_ots, contrnd_ots,
                                self.ctx(context), self.crntctname)
            self._rerun_command(lastcommand)
        elif self.is_add_command(lastcommand):
            self.remove_new_hyp(lastcommand)
        raise StopInference

    def is_add_command(self, command: Any) -> bool:
        """IS-ADD: hook for the SNePSUL layer."""
        return False

    def remove_new_hyp(self, command: Any) -> None:  # pragma: no cover - SNePSUL layer
        return None

    def change_context(self, newnd_supps: Iterable[Context], contrnd_supps: Iterable[Context],
                       newnd_ots: list, contrnd_ots: list, context: Context,
                       context_name: Any) -> tuple:
        newnd_supps = list(newnd_supps)
        contrnd_supps = list(contrnd_supps)
        self._inform_user(newnd_supps, contrnd_supps, context)
        crntct = context.hyps
        unseen = context.hyps
        new_ots = list(newnd_ots)
        for new_supp in newnd_supps:
            new_ot = new_ots[0] if new_ots else None
            new_ots = new_ots[1:]
            contr_ots = list(contrnd_ots)
            for contr_supp in contrnd_supps:
                inc = ns_union(new_supp.hyps, contr_supp.hyps)
                inter = ns_intersect(new_supp.hyps, contr_supp.hyps)
                contr_ot = contr_ots[0] if contr_ots else None
                contr_ots = contr_ots[1:]
                if ns_issubset(inc, crntct):
                    if inter:
                        self._warn_intersection(inter)
                    crntct = ns_union(ns_compl(crntct, inc),
                                      self._make_consistent(inc, self.fullbuildcontext(crntct),
                                                            new_supp, contr_supp, new_ot,
                                                            contr_ot))
                unseen = ns_compl(unseen, inc)
        if unseen:
            crntct = ns_union(ns_compl(crntct, unseen), self._browse_through(unseen, crntct))
        self._change_context_name(crntct, context_name)
        new_hyps = self._add_new_hyps()
        if new_hyps and new_hyps[0] is not None:
            return self._change_context_name(ns_union(crntct, new_hyps), context_name)
        return crntct

    def _change_context_name(self, hyps: tuple, name: Any) -> tuple:
        self.name_ct(self.fullbuildcontext(hyps), name)
        return hyps

    def _inform_user(self, newnd_supps: list, contrnd_supps: list, context: Context) -> None:
        self.write("\n\n In order to make the context consistent you must delete at least"
                   "\n one hypothesis from each of the following sets of hypotheses:")
        hyp_sets: list = []
        for newsupp in newnd_supps:
            targets = [newsupp.hyps] if not contrnd_supps else \
                [ns_union(newsupp.hyps, c.hyps) for c in contrnd_supps]
            for u in targets:
                if ns_issubset(u, context.hyps):
                    hyp_sets.insert(0, u)
                    self.write(f"\n   {self.slight_describe_or_surface_ns(u)}")
        one = [x for hs in hyp_sets for x in hs]
        doubles = _get_doubles(one)
        if doubles:
            if len(doubles) > 1:
                self.write("\n\n  The hypotheses listed below are included in more than"
                           "\n  one set. Removing one of these will make more than one"
                           "\n  set consistent.")
            else:
                self.write("\n\n The hypothesis listed below is included in more than one"
                           "\n  set. Removing it will make more than one set consistent.")
            self.write(f"\n   {self.slight_describe_or_surface_ns(doubles)}")
        self.write("\n\n ")

    def _warn_intersection(self, hyps: tuple) -> None:
        if len(hyps) > 1:
            self.write(" WARNING: the following hypotheses support BOTH contradictory WFFS,"
                       "\n          so removing one of these might be too extreme a revision.\n")
        else:
            self.write(" WARNING: the following hypothesis supports BOTH contradictory WFFS,"
                       "\n          so removing it might be too extreme a revision.\n")
        self._print_lst(hyps)

    def _make_consistent(self, hyps: tuple, context: Context, new_ct: Context,
                         contr_ct: Context, new_ot: Any, contr_ot: Any) -> tuple:
        for _ in range(1000):
            self.write("\n In order to make the context consistent you must delete "
                       "\n at least one hypothesis from the set listed below.\n")
            ct = self._browse_through_hyps(hyps, context.hyps, True)
            if tuple(ct) != tuple(hyps):
                self._negate_hyps(ns_compl(hyps, ct), self.fullbuildcontext(ct), new_ct,
                                  contr_ct, new_ot, contr_ot)
                return ct
        return hyps

    def _negate_hyps(self, disb: tuple, supp: Context, new_supp: Context, contr_supp: Context,
                     new_ot: Any, contr_ot: Any) -> None:
        if len(disb) == 1:
            target = disb[0]
        else:
            k = self.value_to_node(len(disb))
            target = self.find_or_build([("min", (k,)), ("max", (k,)), ("arg", disb)])[0]
        neg = self.negate_n(target)
        ot = combine_ots_star([new_ot, contr_ot]) if new_supp is contr_supp else "ext"
        neg.asupport = ctcs_insert(ot, supp, neg.asupport)

    def _browse_through(self, hyplst: tuple, fullcthyps: tuple) -> tuple:
        self.write("\n The following (not known to be inconsistent) set of "
                   "\n hypotheses was also part of the context where the "
                   "\n contradiction was derived: "
                   f"\n   {self.slight_describe_or_surface_ns(hyplst)}"
                   "\n Do you want to inspect or discard some of them?")
        if self._user_says_yes():
            return self._browse_through_hyps(hyplst, fullcthyps)
        return hyplst

    def _browse_through_hyps(self, hyplst: tuple, fullcthyps: tuple, inc: bool = False) -> tuple:
        oldhyps = hyplst
        removed: tuple = ()
        for _ in range(10000):
            self.write("\n")
            if not hyplst:
                self.write("The set is now empty, but consistent." if inc else "The set is now empty.")
            elif tuple(oldhyps) == tuple(hyplst):
                self.write("An inconsistent set of hypotheses: " if inc
                           else "An unaltered set of hypotheses: ")
            else:
                self.write("The consistent set of hypotheses: " if inc
                           else "The revised set of hypotheses: ")
            self.write("\n")
            self._print_num_lst(hyplst, hyplst)
            n = len(hyplst)
            ans1 = self._offer_choice(n)
            ans2: Any = None
            hyp = None
            if isinstance(ans1, int):
                hyp = hyplst[ans1]
                ans2 = self._lookat_hyp(hyp, fullcthyps)
            elif ans1 == "q":
                return hyplst
            elif ans1 == "i":
                self._menu_instructions(n)
            elif ans1 == "r":
                ans2 = self._see_removed(removed, fullcthyps)
            elif ans1 == "a":
                self._print_fullct(ns_compl(fullcthyps, removed))
            elif ans1 == "d":
                ans2 = self._delete_which(n)
            if isinstance(ans2, int) and not isinstance(ans2, bool):
                hyp = hyplst[ans2]
                hyplst = ns_remove(hyp, hyplst)
                removed = ns_insert(hyp, removed)
            elif isinstance(ans2, Node):
                hyplst = ns_insert(ans2, hyplst)
                removed = ns_remove(ans2, removed)
            elif ans2 == "q":
                return hyplst
            elif ans2 == "d" and hyp is not None:
                hyplst = ns_remove(hyp, hyplst)
                removed = ns_insert(hyp, removed)
        return hyplst

    def _offer_choice(self, n: int) -> Any:
        if n == 0:
            self.write("\n Choose from the menu below:")
        else:
            self.write("\n Enter the list number of a hypothesis to examine or"
                       "\n [d] to discard some hypothesis from this list,")
        self.write("\n [a] to see ALL the hypotheses in the full context,"
                   "\n [r] to see what you have already removed,"
                   "\n [q] to quit revising this set, or "
                   "\n [i] for instructions "
                   "\n\n (please type " + (" " if n == 0 else "a number OR d, ") + "a, r, q or i)")
        for _ in range(100):
            ans = self._br_read()
            if ans is None:
                return "q"
            if isinstance(ans, int):
                if 0 < ans <= n:
                    return ans - 1
                self.write(" Numbers should be from the list above."
                           "\n Enter a number OR a, r, d, q or i: ")
                continue
            for o in "qirad":
                if self._ans_is(ans, o):
                    return o
            self.write("Enter a number from list above OR a, r, d, q or i")
        return "q"

    def _delete_which(self, n: int) -> Any:
        self.write("\n Enter the list number of a hypothesis to discard,"
                   "\n [c] to cancel this discard, or [q] to quit revising this set.")
        for _ in range(100):
            ans = self._br_read()
            if ans is None:
                return "q"
            if isinstance(ans, int):
                if 0 < ans <= n:
                    return ans - 1
                self.write(" Numbers should be from the list above."
                           "\n Enter a number OR c or q")
            elif self._ans_is(ans, "q"):
                return "q"
            elif self._ans_is(ans, "c"):
                return None
        return "q"

    def _lookat_hyp(self, hyp: Node, fullcthyps: tuple) -> Any:
        self.write(f"\n {self.describe_or_surface(hyp)} "
                   f"\n WFFS that depend on {self.slight_describe_or_surface(hyp)}: \n")
        self._print_lst(self._nodes_supported_by(hyp, self.fullbuildcontext(fullcthyps)))
        while True:
            name = self.slight_describe_or_surface(hyp)
            self.write(f"\n What do you want to do with hypothesis {name}?"
                       "\n [d]iscard from the context, [k]eep in the context,"
                       "\n [u]ndecided, [q]uit revising this set, [i]nstructions "
                       "\n (please type d, k, u, q or i)")
            ans = self._read_option("dkuqi", "Please type d, k, u, q or i")
            if ans == "i":
                self._inspect_instructions()
            else:
                return ans

    def _see_removed(self, rlst: tuple, fullcthyps: tuple) -> Any:
        if not rlst:
            self.write("\n There are no removed hypotheses.\n\n")
            return None
        while True:
            self.write("\n Below is a list of hypotheses you have deleted during this revision.\n")
            self._print_num_lst(rlst)
            self.write("\n Enter the list number of a hypothesis to examine and"
                       "\n     possibly return to the set you are revising, or"
                       "\n [r] to return to the set you are revising, or "
                       "\n [q] to quit that set's revision. "
                       "\n\n (please type a number OR r or q)")
            ans = None
            for _ in range(100):
                a = self._br_read()
                if a is None:
                    ans = "q"
                    break
                if isinstance(a, int):
                    if 0 < a <= len(rlst):
                        ans = a - 1
                        break
                    self.write(" Numbers should be from the list above.\n Enter a number OR r or q")
                elif self._ans_is(a, "r") or self._ans_is(a, "q"):
                    ans = a.lower()
                    break
                else:
                    self.write("Enter a number from list above OR r or q")
            if isinstance(ans, int):
                hyp = rlst[ans]
                if self._return_it(hyp, fullcthyps):
                    return hyp
            elif ans == "q":
                return "q"
            else:
                return None

    def _return_it(self, hyp: Node, fullcthyps: tuple) -> bool:
        self.write(f"\n Reviewing the discarded hypothesis:   \n {self.describe_or_surface(hyp)} "
                   f"\n  propositions supported by {self.slight_describe_or_surface(hyp)}: \n")
        self._print_lst(self._nodes_supported_by(hyp, self.fullbuildcontext(fullcthyps)))
        self.write(f"\n Do you want hypothesis {self.slight_describe_or_surface(hyp)} returned "
                   "to the context?\n Enter 'y' or 'n' (if unsure, say 'n')")
        return self._user_says_yes()

    def _menu_instructions(self, n: int) -> None:
        self.write("\n You have the following choices from the menu: "
                   "\n  [a] to see ALL the hypotheses in the full context,"
                   "\n  [r] to see a list of any hypotheses you have already removed"
                   "\n       (you can return one to the set or continue),")
        if n > 0:
            self.write("\n  [d] to discard some hypothesis from this list"
                       "\n       (you'll be prompted for its list number or to cancel or quit),"
                       "\n  [#] where # is the list number (to the left) that corresponds"
                       "\n        to the hypothesis you wish to examine.  This examination"
                       "\n        includes the wffs the hypothesis supports as well as the "
                       "\n        options to keep or discard the hypothesis or to quit this "
                       "revision,")
        self.write("\n  [q] to quit revising this set, or \n  [i] to get these instructions.\n")

    def _inspect_instructions(self) -> None:
        self.write("\n You have five choices from the menu: "
                   "\n  [i] to get these instructions"
                   "\n  [q] to quit revising this set"
                   "\n  [d] to discard this hypothesis from the context and return to inspect "
                   "\n          the rest if the set "
                   "\n  [k] to keep this hypothesis & return to inspect the set as before"
                   "\n  [u] if uncertain what to do with this hypothesis - returns you to"
                   "\n          inspect the set as before \n")

    def _print_fullct(self, hyplst: tuple) -> None:
        self.write("\nAre you sure - the list might be VERY long. (Enter 'y' or 'n')")
        if self._user_says_yes():
            self.write("\n The context as it stands if you quit revising now:\n")
            self._print_lst(hyplst)

    def _print_num_lst(self, lst: Iterable[Node], fullcthyps: Any = None) -> None:
        lst = list(lst)
        for i, hyp in enumerate(lst, 1):
            self.write(f"\n {i} : {self.describe_or_surface(hyp)}")
            if fullcthyps:
                supp = self._nodes_supported_by(hyp, self.fullbuildcontext(tuple(fullcthyps)))
                k = len(supp)
                self.write(f"          ({k} supported proposition{'' if k == 1 else 's'}: "
                           f"{self.slight_describe_or_surface_ns(supp)} )\n")
        self.write("\n")

    def _print_lst(self, lst: Iterable[Node]) -> None:
        for n in lst:
            self.write(f"\n {self.describe_or_surface(n)}")
        self.write("\n")

    def _nodes_supported_by(self, hyp: Node, ct: Context) -> tuple:
        result: tuple = ()
        for nd in self.all_nodes():
            for c in ctcs_to_cts(nd.asupport):
                if ns_ismemb(hyp, c.hyps) and self.issubset_ct(c, ct):
                    result = ns_insert(nd, result)
                    break
        return result

    def _add_new_hyps(self) -> tuple:
        new: tuple = ()
        self.write("\n Do you want to add a new hypothesis?  ")
        add = self._user_says_yes()
        while add:
            h = self._request_new_hyp()
            if h is not None:
                new = ns_insert(h, new)
            self.write("\n Do you want to add another hypothesis?  ")
            add = self._user_says_yes()
        return new

    def _request_new_hyp(self) -> Optional[Node]:
        """Hook: the SNePSUL and SNePSLOG layers read a new hypothesis."""
        return None


def _plist(ns: Iterable[Any]) -> str:
    return "(" + " ".join(str(n) for n in ns) + ")"


def _min_to_front(nodes: list, lt: Callable[[Node, Node], bool]) -> list:
    m = nodes[0]
    for n in nodes[1:]:
        if lt(n, m):
            m = n
    return [m] + [x for x in nodes if x is not m]


def _merge_sort(items: list, pred: Callable[[Any, Any], bool]) -> list:
    """A stable list merge sort taking from the right only when PRED(b, a)."""
    if len(items) <= 1:
        return list(items)
    mid = len(items) // 2
    a = _merge_sort(items[:mid], pred)
    b = _merge_sort(items[mid:], pred)
    out = []
    i = j = 0
    while i < len(a) and j < len(b):
        if pred(b[j], a[i]):
            out.append(b[j])
            j += 1
        else:
            out.append(a[i])
            i += 1
    out.extend(a[i:])
    out.extend(b[j:])
    return out


def _get_doubles(lst: list) -> list:
    seen: list = []
    doubles: list = []
    for x in lst:
        if any(x is d for d in doubles):
            continue
        if any(x is s for s in seen):
            doubles.append(x)
        else:
            seen.append(x)
    return doubles
