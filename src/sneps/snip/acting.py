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
"""SNeRE, the SNePS Rational Engine (``snip/fns/act`` and the
primitive-action files).

An act node is performed by an act process that works through an agenda:
find and test preconditions (achieving them if needed), believe the
effects, then either execute the attached primitive action or find a plan
and perform it.  Control actions (``snsequence``, ``snif``, ``do-all``, ...)
and the mental actions ``believe``/``disbelieve``/``adopt``/``unadopt`` are
provided; new primitive actions are Python callables ``fn(net, act_node)``
attached with :meth:`ActingMixin.attach_primaction`.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Callable, Iterable, Optional

from ..core.network import SNePSError
from ..core.node import Node
from ..core.nodeset import ctcs_to_cts, ns_insert, ns_ismemb, ns_make, ns_union
from .multi import HIGH, INTEND, LOW, Frame, Process
from .structs import OPEN, USER, Channel, chset_insert

CONTROL_ACTIONS = ("achieve", "believe", "snsequence", "snif", "sniterate", "forget",
                   "do-one", "do-all", "withsome", "withall")

START = "START"
DONE = "DONE"


def _plural_choice(n: int, zero: str, one: str, many: str) -> str:
    return zero if n == 0 else one if n == 1 else many


class ActingMixin:
    def _init_acting(self) -> None:
        self.plantrace_mode: Any = None
        self.use_do_acts = True
        self.choose_randomly = True
        import random
        self.rng = random.Random()
        self.most_entrenched_props: tuple = ()

    # ------------------------------------------------------------------
    # primitive actions (act-utils)
    def define_primaction(self, name: str, fn: Callable[[Any, Node], Any]) -> None:
        """Define (or redefine) the primitive action function NAME."""
        self.primaction_functions[name] = fn

    @property
    def primaction_functions(self) -> dict:
        d = self.__dict__.get("_primaction_functions")
        if d is None:
            d = dict(BUILTIN_PRIMACTIONS)
            self.__dict__["_primaction_functions"] = d
        return d

    def attach_primaction(self, node: Any, fname: Any) -> None:
        """Attach the primitive action function FNAME to the action node NODE."""
        if callable(fname) and not isinstance(fname, str):
            fn = fname
            fname = getattr(fn, "__name__", "anonymous")
            self.primaction_functions.setdefault(fname, fn)
        if fname not in self.primaction_functions:
            raise SNePSError(f"{fname} must name a function, but doesn't.")
        if not isinstance(node, Node):
            node = self.value_to_node(node)
        self.primitive_action_functions[node] = fname
        self.primitive_action_functions[("fn", fname)] = node
        self.set_sv("primitive-actions",
                    ns_insert(node, self.value_sv("primitive-actions") or ()))

    def find_action_node(self, action: str) -> Node:
        node = self.primitive_action_functions.get(("fn", action))
        if node is None:
            self.attach_primaction(action, action)
            node = self.node(action)
        return node

    def action_of_act(self, act: Node) -> Optional[Node]:
        ns = act.nodeset("action")
        return ns[0] if ns else None

    def control_action_p(self, act: Node) -> bool:
        return self.primitive_action_functions.get(self.action_of_act(act)) in CONTROL_ACTIONS

    def primact_p(self, act: Node) -> Any:
        """The primitive action function of the action that ACT performs, if any."""
        found = self.find_nodes("action-", (act,))
        return self.primitive_action_functions.get(found[0]) if found else None

    def execute_primaction(self, act: Node) -> Any:
        fname = self.primitive_action_functions.get(self.action_of_act(act))
        if fname is None:
            raise SNePSError(f"No primitive action is attached to {self.action_of_act(act)}")
        return self.primaction_functions[fname](self, act)

    def schedule_act(self, act: Node) -> None:
        if not isinstance(act, Node):
            raise TypeError(f"{act!r} is not a node")
        self.activate_act_n(act)
        pr = self.activation_n(act)
        pr.slots["PRIORITY"] = INTEND
        pr.slots["AGENDA"] = START
        self.initiate(pr)

    def choose_arbitrary_element(self, items: Any) -> Any:
        items = list(items or ())
        if not items:
            return None
        if self.choose_randomly:
            return items[self.rng.randrange(len(items))]
        return items[0]

    def build_act(self, action: str, **cables: Any) -> Node:
        """Find or build the act node (action ACTION, OBJECT1 ...)."""
        cs = [("action", (self.find_action_node(action),))]
        for r, v in cables.items():
            ns = v if isinstance(v, (list, tuple)) else (v,)
            cs.append((r, ns_make(ns)))
        return self.find_or_build(cs)[0]

    def _schedule_built_act(self, act: Node, trace: Optional[str] = None) -> None:
        if trace:
            self.plantrace(trace, (act,), None)
        self.activate_act_n(act)
        pr = self.activation_n(act)
        pr.slots["PRIORITY"] = INTEND
        pr.slots["AGENDA"] = START
        self.initiate(pr)

    # ------------------------------------------------------------------
    # perform
    def perform(self, act: Node, context: Any = None) -> None:
        """Perform the act node ACT."""
        self.clear_infer()
        ctname = context if context is not None else self.value_sv("defaultct")
        with self.let(crntct=ctname):
            self.activate_act_n(act)
            pr = self.activation_n(act)
            pr.slots["PRIORITY"] = INTEND
            pr.slots["AGENDA"] = START
            self.multip(deque([pr]), deque(), deque())

    # ------------------------------------------------------------------
    # the act process (act)
    def p_act(self, f: Frame) -> None:
        node = f.NODE
        pr = self.activation_n(node)
        if self.control_action_p(node):
            self.execute_primaction(node)
            return
        ag = f.AGENDA
        reports = f.REPORTS
        if ag == START:
            self.plantrace("about to do ", (node,), None)
            pr.slots["AGENDA"] = "FIND-PRECONDITIONS"
            self.initiate(pr)
            self.plantrace("i wonder if the act ", (node,), None)
            self.plantrace("has any preconditions...", None, None)
            self._find_for_act(f, "precondition")
        elif ag == "FIND-PRECONDITIONS":
            self.plantrace("the act ", (node,), None)
            n = len(reports or ())
            self.plantrace("has " + _plural_choice(n, "no", "a", "the following")
                           + " precondition" + ("" if n == 1 else "s") + ":", reports, None)
            if reports:
                pr.slots["PRECONDITIONS"] = reports
                pr.slots["REPORTS"] = ()
                pr.slots["AGENDA"] = "TEST-PRECONDITIONS"
                self.initiate(pr)
                self._test_preconditions(pr)
            else:
                pr.slots["AGENDA"] = "FIND-EFFECTS"
                self.initiate(pr)
                self._find_for_act(f, "effect")
        elif ag == "TEST-PRECONDITIONS":
            n = len(f.PRECONDITIONS or ())
            if self._tally_preconditions(f.PRECONDITIONS, reports):
                self.plantrace(_plural_choice(n, "", "it is", "they are") + " satisfied.",
                               None, None)
                pr.slots["REPORTS"] = ()
                pr.slots["AGENDA"] = "FIND-EFFECTS"
                self.initiate(pr)
                self._find_for_act(f, "effect")
            else:
                self.plantrace(_plural_choice(n, "", "it is", "they are") + " not satisfied.",
                               None, None)
                pr.slots["AGENDA"] = START
                pr.slots["REPORTS"] = ()
                self.initiate(pr)
                self._schedule_preconditions(f.PRECONDITIONS)
        elif ag == "FIND-EFFECTS":
            if reports:
                pr.slots["EFFECTS"] = reports
                pr.slots["REPORTS"] = ()
                self._schedule_believe_effects(pr.slots["EFFECTS"])
            pr.slots["AGENDA"] = "EXECUTE"
            self.initiate(pr)
        elif ag == "EXECUTE":
            if self.primact_p(node):
                self.execute_primaction(node)
                pr.slots["AGENDA"] = DONE
            else:
                pr.slots["REPORTS"] = ()
                pr.slots["AGENDA"] = "FIND-PLANS"
                self.initiate(pr)
                self._find_for_act(f, "plan")
        elif ag == "FIND-PLANS":
            self.plantrace("the act ", (node,), None)
            n = len(reports or ())
            self.plantrace("has " + _plural_choice(n, "no", "a", "the following")
                           + " plan" + ("" if n == 1 else "s") + ":", reports, None)
            if reports:
                pr.slots["PLANS"] = reports
                pr.slots["REPORTS"] = ()
                pr.slots["AGENDA"] = DONE
                self._schedule_plans(pr.slots["PLANS"])
            else:
                self.fresh_line()
                self.write(f"WARNING: I don't know how to {self.surface_to_string(node)}\n"
                           "  (this act will be ignored)\n")
            pr.slots["AGENDA"] = DONE

    def surface_to_string(self, node: Node) -> str:
        return str(node)

    def _svar_variable(self, name: str) -> tuple:
        """(unless (and (* 'name) (isvar.n (first (* 'name)))) ($ 'name))"""
        val = self.value_sv(name)
        if not (val and isinstance(val, (tuple, list)) and isinstance(val[0], Node)
                and val[0].is_var):
            v = self.genpvar()
            v.snepslog = name
            self.set_sv(name, (v,))
        return self.value_sv(name)

    def _start_user_query(self, target: Node, client: Process, kind: str = "user",
                          context: Any = None) -> None:
        self.added_nodes = ()
        self.deduction_results = ()
        self.user_process = Process(kind, [], self.crntct, (), None, None, None, 0, 0, client,
                                    HIGH)
        self.activate_n(target)
        pr = self.activation_n(target)
        ct = self.crntct if context is None else context
        pr.slots["REQUESTS"] = chset_insert(Channel((), (), ct, USER, OPEN), pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        self.initiate(pr)

    def _find_for_act(self, f: Frame, rel: str) -> None:
        """FIND-PRECONDITIONS / FIND-EFFECTS / FIND-PLANS"""
        var = self._svar_variable(rel)
        target = self.find_or_build([(rel, ns_make(var)), ("act", (f.NODE,))])[0]
        self._start_user_query(target, self.activation_n(f.NODE))

    def _test_preconditions(self, act_process: Process) -> None:
        self.added_nodes = ()
        self.deduction_results = ()
        self.user_process = Process("user", [], self.crntct, (), None, None, None, 0, 0,
                                    act_process, HIGH)
        for p in act_process.slots["PRECONDITIONS"]:
            precond = p.nodeset("precondition")[0]
            self.activate_n(precond)
            pr = self.activation_n(precond)
            pr.slots["REQUESTS"] = chset_insert(Channel((), (), self.crntct, USER, OPEN),
                                                pr.slots["REQUESTS"])
            pr.slots["PRIORITY"] = LOW
            self.initiate(pr)

    @staticmethod
    def _tally_preconditions(preconds: Any, reports: Any) -> bool:
        reports = tuple(reports or ())
        return all(ns_ismemb(p.nodeset("precondition")[0], reports) for p in preconds or ())

    def _schedule_believe_effects(self, effects: Iterable[Node]) -> None:
        effs = [e.nodeset("effect")[0] if e.nodeset("effect") else None for e in effects]
        if self.use_do_acts:
            believe_acts: list = []
            for eff in effs:
                if eff is not None:
                    believe_acts.insert(0, self.build_act("believe", object1=eff))
            do_all = self.build_act("do-all", object1=tuple(believe_acts))
            self._schedule_built_act(do_all)
        else:
            for eff in effs:
                self._schedule_built_act(self.build_act("believe", object1=eff))

    def _schedule_preconditions(self, preconds: Iterable[Node]) -> None:
        pres = [p.nodeset("precondition")[0] for p in preconds]
        if self.use_do_acts:
            achieve_acts: list = []
            for pre in pres:
                achieve_acts.insert(0, self.build_act("achieve", object1=pre))
            do_all = self.build_act("do-all", object1=tuple(achieve_acts))
            self._schedule_built_act(do_all, "Intending to do")
        else:
            for pre in pres:
                self._schedule_built_act(self.build_act("achieve", object1=pre), "Intending to do")

    def _schedule_plans(self, plans: Iterable[Node]) -> None:
        plan_list = [p.nodeset("plan")[0] for p in plans]
        if self.use_do_acts:
            do_one = self.build_act("do-one", object1=tuple(plan_list))
            self._schedule_built_act(do_one, "Intending to do")
        else:
            self._schedule_built_act(self.choose_arbitrary_element(plan_list))

    # ------------------------------------------------------------------
    # tracing (plantrace)
    def plantrace(self, msg: str, nodeset: Any, restriction: Any) -> None:
        mode = self.plantrace_mode
        if not mode:
            return
        if callable(mode):
            mode(self, msg, nodeset, restriction)
            return
        self.fresh_line()
        self.write("\n" + _expand_tildes(self, msg))
        if mode == "surface":
            for n in nodeset or ():
                self.surface([n])
        elif nodeset:
            self.pp_nodetree([self._plantrace_desc(n, restriction) for n in nodeset])

    def _plantrace_desc(self, node: Any, restriction: Any) -> Any:
        sbst = tuple(restriction or ())
        if not isinstance(node, Node):
            return node
        if node.is_base:
            return node.to_number() if node.is_number() else [node]
        if node.is_var:
            t = next((p[1] for p in sbst if p[0] is node), None)
            if t is not None:
                return [node, "<--", self._plantrace_desc(t, restriction)
                        if self.plantrace_mode == "full-trace" else t]
            return node
        return [node] + [[r] + [self._plantrace_desc(n, restriction) for n in ns]
                         for r, ns in self.n_to_downcs(node)]

    # ------------------------------------------------------------------
    # mental actions (mental-acts)
    def believe_propositions(self, props: Iterable[Node]) -> tuple:
        props = ns_make(props)
        self.most_entrenched_props = props
        for p in props:
            if self.isassert(p):
                self.plantrace("I already believe ", (p,), None)
            else:
                self.assert_n(p, self.crntct)
                self.sv_add("assertions", p)
                self.plantrace("Believe ", (p,), None)
        return self.dynamic_add_star(props)

    def disbelieve_propositions(self, props: Iterable[Node]) -> None:
        for p in props or ():
            ctxs = ctcs_to_cts(p.asupport)
            self.autobr(ctxs, ctxs, self.get_context(self.crntct), None, None)

    def find_nodes(self, *pairs: Any) -> list:
        """The nodes that SNePSUL ``find`` finds with PAIRS: alternating paths
        (relation names or path lists) and node sets."""
        from ..core.build import ns_to_nbs

        def find() -> tuple:
            consts: list = []
            for i in range(0, len(pairs), 2):
                nodes = (pairs[i + 1],) if isinstance(pairs[i + 1], Node) else pairs[i + 1]
                ns: tuple = ()
                for n in nodes:
                    ns = ns_union(ns, (n,))
                consts.insert(0, (self.checkpath_form(pairs[i]), ns_to_nbs(ns)))
            ct = self.crntcontext(None)
            with self.let(crntct=ct):
                return tuple(self.in_context_ns(self.nbs_to_ns(self.find_nbs(consts, [])), None))
        return list(self.topsneval(find).value or ())


# ----------------------------------------------------------------------
# the built-in primitive actions

def _object1(net: Any, act: Node) -> tuple:
    return net.pathfrom(["object1"], act)


def pa_believe(net: Any, act: Node) -> Any:
    if not act.nodeset("object1"):
        raise SNePSError("Attempt to perform believe with no proposition.", "snip", "believe")
    return net.believe_propositions(act.nodeset("object1"))


def pa_disbelieve(net: Any, act: Node) -> Any:
    return net.disbelieve_propositions(act.nodeset("object1"))


def pa_adopt(net: Any, act: Node) -> Any:
    policies = act.nodeset("object1")
    if not policies:
        raise SNePSError("Attempt to perform adopt with no policy.", "snip", "adopt")
    for policy in policies:
        if net.isassert(policy):
            net.plantrace("I already intend ", (policy,), None)
        else:
            ct = net.crntct
            net.topsneval(lambda p=policy, ct=ct: net.assert_nodes(
                (p,), net.crntcontext([ct]) if isinstance(ct, str) else ct))
            net.plantrace("Adopt ", (policy,), None)
    return net.dynamic_add_star(policies)


def pa_unadopt(net: Any, act: Node) -> None:
    for policy in act.nodeset("object1"):
        if net.isassert(policy):
            ct = net.get_context(net.crntct)
            if ct is not None and ns_ismemb(policy, ct.hyps):
                net.plantrace("Unadopt ", (policy,), None)
                net.remove_hyps_silently((policy,), net.crntct)
            else:
                net.plantrace("Can't unadopt derived policy ", (policy,), None)
        else:
            net.plantrace("already didn't intend ", (policy,), None)


def pa_do_all(net: Any, act: Node) -> None:
    all_acts = _object1(net, act)
    pr = net.activation_n(act)
    net.plantrace("Now doing: DO-ALL ", all_acts, None)
    if all_acts:
        for a in all_acts:
            net.schedule_act(a)
    else:
        net.plantrace("Nothing to do", (), None)
    pr.slots["AGENDA"] = DONE


def pa_do_one(net: Any, act: Node) -> None:
    possible = _object1(net, act)
    chosen = net.choose_arbitrary_element(possible)
    pr = net.activation_n(act)
    net.plantrace("Now doing: DO-ONE ", possible, None)
    if chosen is not None:
        net.plantrace("Chose to do the act ", (chosen,), None)
        net.schedule_act(chosen)
    else:
        net.plantrace("Nothing to do", (), None)
    pr.slots["AGENDA"] = DONE


def pa_snsequence(net: Any, act: Node) -> None:
    pr = net.activation_n(act)
    pr.slots["AGENDA"] = DONE
    all_acts: list = []
    i = 0
    while True:
        i += 1
        acts = act.nodeset(f"object{i}")
        if not acts:
            break
        all_acts = list(acts) + all_acts
    for a in all_acts:
        net.activate_act_n(a)
        p = net.activation_n(a)
        p.slots["PRIORITY"] = INTEND
        p.slots["AGENDA"] = START
        net.initiate(p)


def _test_conditions(net: Any, act_process: Process) -> None:
    conditions = net.pathfrom(["object1", "condition"], act_process.slots["NODE"])
    net.added_nodes = ()
    net.deduction_results = ()
    net.user_process = Process("posuser", [], net.crntct, (), None, None, None, 0, 0,
                               act_process, HIGH)
    for c in conditions:
        net.activate_n(c)
        pr = net.activation_n(c)
        pr.slots["REQUESTS"] = chset_insert(Channel((), (), net.crntct, USER, OPEN),
                                            pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        net.initiate(pr)


def _schedule_then_acts(net: Any, acts: Iterable[Node]) -> None:
    act = net.build_act("do-one", object1=tuple(acts))
    net._schedule_built_act(act, "I intend to do:")


def _snif_like(net: Any, n: Node, iterate: bool) -> None:
    n_act = net.activation_n(n)
    ag = n_act.slots["AGENDA"]
    if ag == START:
        net.plantrace(("now doing: sniterate " if iterate else "now doing: snif "), (n,), None)
        n_act.slots["AGENDA"] = "TEST"
        net.initiate(n_act)
        _test_conditions(net, n_act)
    elif ag == "TEST":
        reports = net.f.REPORTS if net.f is not None else ()
        k = len(reports or ())
        if iterate:
            msg = _plural_choice(k, "no condition is", "this is", "the following are")
        else:
            msg = _plural_choice(k, "No condition is", "This is", "The following are")
        net.plantrace(msg + " satisfied:", reports, None)
        n_act.slots["AGENDA"] = DONE
        if reports:
            guarded = net.find_nodes("object1-", (n,), "condition", tuple(reports))
            acts = net.find_nodes("then-", tuple(guarded)) if guarded else []
            if iterate:
                n_act.slots["REPORTS"] = ()
                n_act.slots["AGENDA"] = START
                do_one = net.build_act("do-one", object1=tuple(acts))
                seq = net.build_act("snsequence", object1=do_one, object2=n)
                net._schedule_built_act(seq, "I intend to do:")
            else:
                _schedule_then_acts(net, acts)
        else:
            elseact = net.find_nodes(["compose", "else-", "object1-"], (n,))
            if elseact:
                net.schedule_act(elseact[0])


def pa_snif(net: Any, act: Node) -> None:
    _snif_like(net, act, False)


def pa_sniterate(net: Any, act: Node) -> None:
    _snif_like(net, act, True)


def pa_achieve(net: Any, n: Node) -> None:
    prop = net.pathfrom(["object1"], n)[0]
    n_act = net.activation_n(n)
    ag = n_act.slots["AGENDA"]
    if ag == START:
        net.plantrace("Want to achieve ", (prop,), None)
        if net.isassert(prop):
            net.plantrace("~&~%Already Achieved.~%", None, None)
            n_act.slots["AGENDA"] = DONE
        else:
            n_act.slots["AGENDA"] = "FIND-PLANS"
            net.initiate(n_act)
            net.plantrace("Want to find a plan to achieve", (prop,), None)
            var = net._svar_variable("gplan")
            target = net.find_or_build([("plan", ns_make(var)), ("goal", (prop,))])[0]
            net._start_user_query(target, net.activation_n(n), "user",
                                  net.get_context(net.crntct))
    elif ag == "FIND-PLANS":
        plans = n_act.slots["REPORTS"]
        k = len(plans or ())
        msg = ("The goal cannot be achieved. " if k == 0 else
               "The goal can be achieved. by the following plan" + ("" if k == 1 else "s")
               + ": ")
        net.plantrace(msg, plans, None)
        if plans:
            n_act.slots["AGENDA"] = DONE
            net._schedule_plans(plans)
        else:
            net.plantrace("No plans found to achieve:", (prop,), None)


def _with_act(net: Any, n: Node, every: bool) -> None:
    designator = net.pathfrom(["suchthat"], n)[0]
    do_act = net.pathfrom(["do"], n)[0]
    with_act = net.activation_n(n)
    ag = with_act.slots["AGENDA"]
    if ag == START:
        net.plantrace("Now doing: WITHALL " if every else "Now doing: WITHSOME ", (n,), None)
        with_act.slots["AGENDA"] = "IDENTIFY-OBJECTS"
        net.initiate(with_act)
        net.added_nodes = ()
        net.deduction_results = ()
        net.user_process = Process("posuser", [], net.crntct, (), None, None, None, 0, 0,
                                   net.activation_n(n), HIGH)
        net.activate_n(designator)
        pr = net.activation_n(designator)
        pr.slots["REQUESTS"] = chset_insert(Channel((), (), net.crntct, USER, OPEN),
                                            pr.slots["REQUESTS"])
        pr.slots["PRIORITY"] = LOW
        net.initiate(pr)
    elif ag == "IDENTIFY-OBJECTS":
        reports = [r for r in (net.f.REPORTS if net.f is not None else ()) if net.isassert(r)]
        with_act.slots["AGENDA"] = DONE
        if reports:
            net.plantrace("The designator", (designator,), None)
            net.plantrace("is effective on the following:", reports, None)
            net.plantrace("for the act:", (do_act,), None)
            acts: list = []
            for report in reports:
                sublist, _new = net.unify(designator, report)
                substs = sublist[0][0] if sublist else ()
                a = net.applysubst(do_act, substs)
                if not a.is_pat:
                    acts.insert(0, a)
            if every:
                net._schedule_built_act(net.build_act("do-all", object1=tuple(acts)),
                                        "I intend to do:")
            else:
                _schedule_then_acts(net, acts)
        else:
            net.plantrace("No designators found!", None, None)
            acts2 = net.find_nodes("else-", (n,))
            if acts2:
                net.schedule_act(acts2[0])


def pa_withsome(net: Any, act: Node) -> None:
    _with_act(net, act, False)


def pa_withall(net: Any, act: Node) -> None:
    _with_act(net, act, True)


BUILTIN_PRIMACTIONS = {
    "believe": pa_believe,
    "disbelieve": pa_disbelieve,
    "forget": pa_disbelieve,
    "adopt": pa_adopt,
    "unadopt": pa_unadopt,
    "do-all": pa_do_all,
    "do-one": pa_do_one,
    "snsequence": pa_snsequence,
    "snif": pa_snif,
    "sniterate": pa_sniterate,
    "achieve": pa_achieve,
    "withsome": pa_withsome,
    "withall": pa_withall,
}


def _expand_tildes(net: Any, msg: str) -> str:
    """The FORMAT directives used in plan-trace messages (~% and ~&)."""
    out = []
    i = 0
    while i < len(msg):
        c = msg[i]
        if c == "~" and i + 1 < len(msg):
            d = msg[i + 1]
            if d == "%":
                out.append("\n")
                i += 2
                continue
            if d == "&":
                if out and not "".join(out).endswith("\n"):
                    out.append("\n")
                i += 2
                continue
            if d == "~":
                out.append("~")
                i += 2
                continue
        out.append(c)
        i += 1
    return "".join(out)
