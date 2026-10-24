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
"""The SNePSUL commands (from SNePS 2.8 ``sneps/fns``, ``snip/fns``,
``snebr`` and ``multi``).

Each command receives the network and its argument list (SNePSUL data as
read, unless the command evaluates its arguments) and returns a
:class:`~sneps.snepsul.evaluator.Result`: its value and the context used.
"""

from __future__ import annotations

from typing import Any

from ..core.network import SNePSError
from ..core.nodeset import ns_compl, ns_intersect, ns_union
from ..core.printing import Binding
from .evaluator import Result, _is, _is_kw, define_command, sym_name
from .reader import PythonCode


def _V(result: Any, ctx: Any = None) -> Result:
    return Result(result, ctx)


def _as_list(x: Any) -> list:
    if x is None:
        return []
    return list(x) if isinstance(x, (list, tuple)) else [x]


def _defaultct(net: Any) -> Any:
    return net.value_sv("defaultct")


# ----------------------------------------------------------------------
# build / assert

@define_command("build", ("ns", "bns", "fns"))
def c_build(net: Any, snd: list) -> Result:
    return _V(net.find_or_build(net.evalsnd(snd, True)), _defaultct(net))


def _assert(net: Any, snd: list) -> Result:
    ct = net.processcontextdescr(snd)
    with net.let(crntct=ct):
        ns = net.nseval(["build"] + net.getsndescr(snd))
        return _V(net.assert_nodes(ns, ct), ct)


define_command("assert", ("top", "ns", "bns", "fns"))(_assert)
define_command("adopt", ("top", "ns", "bns", "fns"))(_assert)


@define_command("!", ("top", "rearrange", "ns", "bns", "tbns", "fns"))
def c_bang(net: Any, args: list) -> Result:
    ct = net.processcontextdescr(args)
    with net.let(crntct=ct):
        return _V(net.assert_nodes(net.nseval(net.getsndescr(args)), ct), ct)


# ----------------------------------------------------------------------
# find

@define_command("find", ("top", "ns", "bns", "tbns", "fns"))
def c_find(net: Any, snd: list) -> Result:
    return net.find_command(snd)


@define_command("findassert", ("top", "ns", "bns", "tbns", "fns"))
def c_findassert(net: Any, snd: list) -> Result:
    return net.find_command(snd, lambda n: net.isassert(n))


@define_command("findconstant", "findassert")
def c_findconstant(net: Any, snd: list) -> Result:
    return net.find_command(snd, lambda n: n.is_mol)


@define_command("findpattern", "findassert")
def c_findpattern(net: Any, snd: list) -> Result:
    return net.find_command(snd, lambda n: n.is_pat)


@define_command("findbase", "findassert")
def c_findbase(net: Any, snd: list) -> Result:
    return net.find_command(snd, lambda n: n.is_base)


@define_command("findvariable", "findassert")
def c_findvariable(net: Any, snd: list) -> Result:
    return net.find_command(snd, lambda n: n.is_var)


@define_command("list-nodes", "find")
def c_list_nodes(net: Any, args: list) -> Result:
    ct = sym_name(args[0]) if args else _defaultct(net)
    with net.let(crntct=ct):
        return _V(tuple(net.in_context_ns(net.all_nodes(), True)), ct)


@define_command("list-hypotheses", "find")
def c_list_hypotheses(net: Any, args: list) -> Result:
    ct = sym_name(args[0]) if args else _defaultct(net)
    c = net.get_context(ct)
    return _V(c.hyps if c else (), ct)


@define_command("beliefs-about", ("top", "ns", "bns", "fns"))
def c_beliefs_about(net: Any, exp: list) -> Result:
    ct = net.processcontextdescr(exp)
    with net.let(crntct=ct):
        ns = tuple(net.in_context_ns(net.nseval(net.getsndescr(exp)), ct))
        dominating: tuple = ()
        for n in ns:
            dominating = ns_union(net.dominatingnodes(n), dominating)
        return _V(tuple(n for n in ns_union(ns, dominating) if net.isassert(n)), ct)


# ----------------------------------------------------------------------
# describe and friends

def _describe(net: Any, exp: list, full: bool) -> Result:
    ct = net.processcontextdescr(exp)
    with net.let(crntct=ct):
        given = net.iscontext_given(exp) if full else ct
        ns = net.in_context_ns(net.nseval(net.getsndescr(exp)), given)
        net.describe_nodes(ns, full)
        return _V(tuple(ns), ct)


@define_command("describe", ("top", "ns", "bns", "tbns", "fns"))
def c_describe(net: Any, exp: list) -> Result:
    return _describe(net, exp, False)


@define_command("full-describe", "describe")
def c_full_describe(net: Any, exp: list) -> Result:
    return _describe(net, exp, True)


@define_command("dump", "describe")
def c_dump(net: Any, exp: list) -> Result:
    ct = net.processcontextdescr(exp)
    with net.let(crntct=ct):
        ns = net.in_context_ns(net.nseval(net.getsndescr(exp)), ct)
        net.dump_nodes(ns)
        return _V(tuple(ns), ct)


@define_command("surface")
def c_surface(net: Any, exp: list) -> Result:
    hook = getattr(net, "surface_command", None)
    if hook is not None:
        return hook(exp)
    return _describe(net, exp, True)


@define_command("show", ("top", "ns", "bns", "tbns", "fns"))
def c_show(net: Any, exp: list) -> Result:
    fname = None
    k = 0
    nodes_exp = []
    while k < len(exp):
        if _is_kw(exp[k], "file") and k + 1 < len(exp):
            fname = sym_name(exp[k + 1])
            k += 2
        elif _is_kw(exp[k], "format") and k + 1 < len(exp):
            k += 2
        else:
            nodes_exp.append(exp[k])
            k += 1
    ct = net.processcontextdescr(nodes_exp)
    with net.let(crntct=ct):
        ns = net.nseval(net.getsndescr(nodes_exp))
        dot = net.to_dot(ns)
    path = (fname or "sneps-graph") + ".dot"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dot)
    net.fresh_line()
    net.write(f"\nGraph written to {path} (render it with GraphViz: dot -Tpng {path})\n")
    return _V(tuple(ns), ct)


# ----------------------------------------------------------------------
# relations and paths

@define_command("define", ("top", "ns", "bns", "tbns", "rs"))
def c_define(net: Any, args: list) -> Result:
    out = []
    for r in args:
        name = sym_name(r)
        if name.endswith("-"):
            net.beep()
            net.write(f'{name}:  It is illegal to define a relation ending with "-".\n')
        elif net.is_r(name):
            net.beep()
            net.write(f"{name} is already defined.\n")
            out.append(name)
        else:
            net.new_r(name)
            out.append(name)
    return _V(out or None, net.buildcontext(()))


@define_command("undefine")
def c_undefine(net: Any, args: list) -> Result:
    rs = net.rseval(args)
    rels = rs if isinstance(rs, list) else ([rs] if rs else [])
    for r in rels:
        net.undefine_r(r)
    net.write("\nRelations undefined: " + "".join(f"{r} " for r in rels) + "\n")
    return Result()


@define_command("define-path")
def c_define_path(net: Any, args: list) -> Result:
    for k in range(0, len(args) - 1, 2):
        net.define_path(sym_name(args[k]), net.to_path(args[k + 1]))
    return Result()


@define_command("undefine-path")
def c_undefine_path(net: Any, args: list) -> Result:
    net.undefine_path([sym_name(a) for a in args])
    return _V(list(args) or None)


# ----------------------------------------------------------------------
# erase / resetnet

@define_command("erase")
def c_erase(net: Any, args: list) -> Result:
    net.erase(net.nseval(args))
    return Result()


@define_command("silent-erase")
def c_silent_erase(net: Any, args: list) -> Result:
    net.erase(net.nseval(args), silent=True)
    return Result()


@define_command("resetnet", ("top",), eval_args=True)
def c_resetnet(net: Any, args: list) -> Result:
    net.resetnet(bool(args and args[0] is not None and args[0] is not False))
    return Result()


# ----------------------------------------------------------------------
# infix and variable commands

@define_command("=", ("top", "rearrange", "ns", "bns", "tbns", "fns"))
def c_assign(net: Any, args: list) -> Result:
    ns = net.nseval(args[0])
    sv = sym_name(args[1]) if len(args) > 1 else None
    if sv is not None and net.issys_sv(sv):
        raise SNePSError(f"Attempting to change value of system variable {sv}",
                         "assigment operator", "=")
    if sv is not None:
        net.set_sv(sv, ns)
    return _V(ns, _defaultct(net))


@define_command("+", "=")
def c_union(net: Any, args: list) -> Result:
    res: tuple = ()
    sets = [net.buildeval(a, True) for a in args]
    if sets:
        res = sets[0]
        for s in sets[1:]:
            res = ns_union(res, s)
    return _V(res, _defaultct(net))


@define_command("&", "=")
def c_intersection(net: Any, args: list) -> Result:
    sets = [net.buildeval(a, True) for a in args]
    res: tuple = ()
    if sets:
        res = sets[0]
        for s in sets[1:]:
            res = ns_intersect(res, s)
    return _V(res, _defaultct(net))


@define_command("-", "=")
def c_difference(net: Any, args: list) -> Result:
    a = net.nseval(args[0]) if args else ()
    b = net.nseval(args[1]) if len(args) > 1 else ()
    return _V(ns_compl(a, b), _defaultct(net))


@define_command(">", ("top", "rearrange", "rs"))
def c_rs_assign(net: Any, args: list) -> Result:
    rs = net.rseval(args[0])
    net.set_sv(sym_name(args[1]), rs)
    return _V(rs, _defaultct(net))


@define_command("_", "=")
def c_exceptrels(net: Any, args: list) -> Result:
    ns = net.nseval(args[0])
    rs = net.rseval(args[1]) if len(args) > 1 else None
    rels = rs if isinstance(rs, list) else ([rs] if rs else [])
    if rels:
        ns = tuple(n for n in ns if not any(n.nodeset(r) for r in rels))
    return _V(ns, _defaultct(net))


@define_command("*", ("top", "ns", "bns", "tbns", "fns", "rs"), eval_args=True)
def c_star(net: Any, args: list) -> Result:
    v = net.value_sv(sym_name(args[0]))
    return _V(v, _defaultct(net))


@define_command("$", ("bns",), eval_args=True)
def c_dollar(net: Any, args: list) -> Any:
    name = sym_name(args[0])
    v = net.genpvar()
    v.snepslog = name
    return net.set_sv(name, (v,))


@define_command("#", "$", eval_args=True)
def c_hash(net: Any, args: list) -> Any:
    return net.set_sv(sym_name(args[0]), (net.genpbase(),))


# ----------------------------------------------------------------------
# Python escapes and leaving the top level

@define_command("^", ("top", "ns", "bns", "tbns", "fns", "rs"))
def c_caret(net: Any, args: list) -> Result:
    """(^ expr): the value of the Python expression EXPR."""
    v = net.python.evaluate(args[0].source) if args and isinstance(args[0], PythonCode) else None
    return _V(v, _defaultct(net))


@define_command("exit")
def c_exit(net: Any, args: list) -> Any:
    """(exit): leave the SNePS top level."""
    net._exit_flag = True
    return None


@define_command("copyright")
def c_copyright(net: Any, args: list) -> Any:
    net.write("""
  SNePS 2.8: Copyright (C) 1984--2013 Research Foundation of State University
  of New York, on behalf of University at Buffalo.  PySNePS is a Python
  translation of SNePS 2.8 distributed under the University at Buffalo
  Public License Version 1.0 (see the file COPYING).""")
    return None


@define_command("clear-infer-all")
def c_clear_infer_all(net: Any, args: list) -> Any:
    net.clear_infer_all()
    return "All node activations removed."


@define_command("clear-infer")
def c_clear_infer(net: Any, args: list) -> Any:
    net.clear_infer()
    return "Node activation cleared. Some register information retained."


# ----------------------------------------------------------------------
# contexts

@define_command("describe-context")
def c_describe_context(net: Any, args: list) -> Result:
    net.describe_context(sym_name(args[0]) if args else None)
    return Result()


@define_command("set-context")
def c_set_context(net: Any, args: list) -> Result:
    net.set_context(net.nseval(args[0]), sym_name(args[1]) if len(args) > 1 else None)
    return Result()


@define_command("add-to-context")
def c_add_to_context(net: Any, args: list) -> Result:
    net.add_to_context(net.nseval(args[0]), sym_name(args[1]) if len(args) > 1 else None)
    return Result()


@define_command("remove-from-context")
def c_remove_from_context(net: Any, args: list) -> Result:
    ct = net.remove_from_context(net.nseval(args[0]), sym_name(args[1]) if len(args) > 1 else None)
    return Result(ct)


@define_command("list-context-names")
def c_list_context_names(net: Any, args: list) -> Result:
    net.list_context_names()
    return Result()


@define_command("set-default-context")
def c_set_default_context(net: Any, args: list) -> Result:
    net.set_default_context(sym_name(args[0]))
    return Result()


# ----------------------------------------------------------------------
# inference

def _numberfield(x: Any) -> bool:
    if isinstance(x, int) and not isinstance(x, bool):
        return True
    return (isinstance(x, list) and len(x) == 2 and all(isinstance(e, int) for e in x))


def _deduce_cmd(fn_name: str, dedup: bool = False):
    def cmd(net: Any, snd: list) -> Result:
        nf = snd[0] if snd and _numberfield(snd[0]) else None
        rest = snd[1:] if nf is not None else snd
        sd = net.getsndescr(rest)
        ct = net.processcontextdescr(rest)
        with net.let(crntct=ct, crntctname=ct):
            targets = net.nseval(["build"] + sd)
            res = getattr(net, fn_name)(nf, targets)
        if dedup:
            out: list = []
            for k, e in enumerate(res):
                if not any(_entry_eq(e, x) for x in res[k + 1:]):
                    out.append(e)
            return _V([[Binding(p[0], p[1]) for p in e] for e in out] or None, ct)
        return _V(res, ct)
    return cmd


def _entry_eq(a: Any, b: Any) -> bool:
    return len(a) == len(b) and all(x[0] == y[0] and x[1] is y[1] for x, y in zip(a, b))


define_command("deduce", ("top", "ns", "bns", "tbns", "fns"))(_deduce_cmd("deduce_star"))
define_command("deducetrue", ("top", "ns", "bns", "tbns", "fns"))(_deduce_cmd("deducetrue_star"))
define_command("deducefalse", ("top", "ns", "bns", "tbns", "fns"))(_deduce_cmd("deducefalse_star"))
define_command("deducewh", ("top", "ns", "bns", "tbns", "fns"))(_deduce_cmd("deducewh_star", True))
define_command("deducewhnot", ("top", "ns", "bns", "tbns", "fns"))(_deduce_cmd("deducewhnot_star", True))


@define_command("add", ("top", "ns", "bns", "fns"))
def c_add(net: Any, snd: list) -> Result:
    ct = net.processcontextdescr(snd)
    with net.let(crntct=ct, crntctname=ct):
        return _V(net.add_star(net.nseval(["assert"] + list(snd))), ct)


@define_command("dynamic-add", "add")
def c_dynamic_add(net: Any, snd: list) -> Result:
    ct = net.processcontextdescr(snd)
    with net.let(crntct=ct, crntctname=ct):
        return _V(net.dynamic_add_star(net.nseval(["assert"] + list(snd))), ct)


@define_command("activate", ("top", "ns", "bns", "fns"))
def c_activate(net: Any, exp: list) -> Result:
    ct = net.processcontextdescr(exp)
    with net.let(crntct=ct, crntctname=ct):
        ns = tuple(net.in_context_ns(net.nseval(net.getsndescr(exp)), ct))
        dominating: tuple = ()
        for n in ns:
            dominating = ns_union(net.dominatingnodes(n), dominating)
        dominating = tuple(n for n in dominating if net.isassert(n))
        sent = ns_union(ns, dominating)
        added = net.add_star(sent)
        return _V(ns_compl(ns_union(ns, tuple(added)), dominating), ct)


@define_command("perform", "add")
def c_perform(net: Any, args: list) -> Result:
    net.clear_infer()
    ct = net.processcontextdescr(args[1:])
    with net.let(crntct=ct, crntctname=ct):
        acts = net.nseval(args[0])
        if acts:
            from collections import deque
            act = acts[0]
            net.activate_act_n(act)
            pr = net.activation_n(act)
            pr.slots["PRIORITY"] = "INTEND"
            pr.slots["AGENDA"] = "START"
            net.multip(deque([pr]), deque(), deque())
    return Result()


# ----------------------------------------------------------------------
# belief revision settings

@define_command("br-mode")
def c_br_mode(net: Any, args: list) -> Any:
    flag = args[0] if args else None
    net.br_auto_mode = flag is not None and flag is not False and not _is(flag, "nil")
    return flag


@define_command("br-tie-mode")
def c_br_tie_mode(net: Any, args: list) -> Any:
    flag = args[0] if args else None
    net.br_tie_mode = flag is not None and flag is not False and not _is(flag, "nil")
    return flag


@define_command("set-order")
def c_set_order(net: Any, args: list) -> Any:
    name = sym_name(args[0]) if args and args[0] is not None else "null-order"
    fn = net.br_orders.get(name.lower())
    if fn is None:
        # an order defined in Python: f(p, q) is true if p is less or
        # equally entrenched than q
        user_fn = net.python.namespace.get(name)
        if not callable(user_fn):
            raise SNePSError(f"{name} is neither a known order nor a Python function",
                             "snebr", "set-order")
        fn = lambda _net, a, b: bool(user_fn(a, b))
    net.br_totalorder = fn
    return args[0]


# ----------------------------------------------------------------------
# MULTI tracing

def _record(flag: Any, add: list) -> Any:
    if not add and not flag:
        return True
    if add and not isinstance(flag, list):
        return add
    if add:
        return add + flag
    return flag


def _forget(flag: Any, rem: list) -> Any:
    if not rem or not isinstance(flag, list):
        return None
    out = [x for x in flag if x not in rem]
    return out or None


@define_command("ev-trace")
def c_ev_trace(net: Any, args: list) -> Any:
    names = [sym_name(a).lower() for a in args]
    net.trace_events = _record(net.trace_events, names)
    return net.trace_events


@define_command("unev-trace")
def c_unev_trace(net: Any, args: list) -> Any:
    net.trace_events = _forget(net.trace_events, [sym_name(a).lower() for a in args])
    return None


@define_command("in-trace")
def c_in_trace(net: Any, args: list) -> Any:
    net.trace_initiated = _record(net.trace_initiated, [sym_name(a).lower() for a in args])
    return net.trace_initiated


@define_command("unin-trace")
def c_unin_trace(net: Any, args: list) -> Any:
    net.trace_initiated = _forget(net.trace_initiated, [sym_name(a).lower() for a in args])
    return None


# ----------------------------------------------------------------------
# input files

@define_command("demo")
def c_demo(net: Any, args: list) -> Result:
    if not args:
        net.demo_menu()
        return Result()
    if len(args) > 1:
        pause = args[1]
        net.start_demo(sym_name(args[0]), None if pause is None or _is(pause, "nil")
                       else sym_name(pause).lower())
    else:
        net.start_demo(sym_name(args[0]))
    return Result()


@define_command("intext")
def c_intext(net: Any, args: list) -> Result:
    fname = sym_name(args[0])
    net.fresh_line()
    net.write(f"Loading file {fname}.\n")
    net.sneps_load(fname)
    return Result()


# ----------------------------------------------------------------------
# saving and restoring networks (in PySNePS' JSON format)

@define_command("outnet", ("top",), eval_args=True)
def c_outnet(net: Any, args: list) -> Result:
    from ..io import save_network
    fname = sym_name(args[0])
    save_network(net, net.translate_path(fname))
    net.write(f"\n\nNetwork dumped to file: {fname}\n")
    return Result()


@define_command("innet", ("top",), eval_args=True)
def c_innet(net: Any, args: list) -> Result:
    from ..io import load_network
    fname = sym_name(args[0])
    load_network(net, net.translate_path(fname))
    net.write(f"\n\nNetwork loaded from file: {fname}\n")
    return Result()


# ----------------------------------------------------------------------
# relational database operations

@define_command("dbproject")
def c_dbproject(net: Any, args: list) -> Any:
    nodeset = net.nseval(args[0])
    rels = args[1:]
    out: list = []
    for nde in nodeset:
        row: list = []
        for rel in rels:
            found = net.find_nodes(["converse", net.checkpath_form(rel)], (nde,))
            row.extend([rel, list(found) or None])
        if not any(_rows_equal(row, r) for r in out):
            out.append(row)
    return out or None


def _rows_equal(a: list, b: list) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if isinstance(x, list) and isinstance(y, list):
            if len(x) != len(y) or any(p is not q for p, q in zip(x, y)):
                return False
        elif x != y and not (x is None and y is None):
            return False
    return True


@define_command("dbjoin")
def c_dbjoin(net: Any, args: list) -> Any:
    jrel, ns1, rels1, ns2, rels2 = args
    compose_bang = ["compose", "!"]
    snd = [compose_bang, ns1, compose_bang, ["?", "jvar1"],
           ["compose", jrel, ["converse", jrel]],
           ["find", compose_bang, ns2, compose_bang, ["?", "jvar2"]]]
    consts, qvars = net.fevalsnd(snd)
    out: list = []
    for node, bs in net.find_nbs(consts, qvars):
        b = dict(bs)
        n1 = (b.get("jvar1") or (None,))[0]
        n2 = (b.get("jvar2") or (None,))[0]
        row: list = []
        for rel in _as_list(rels1):
            row.extend([rel, list(net.find_nodes(["converse", net.checkpath_form(rel)], (n1,))) or None])
        for rel in _as_list(rels2):
            row.extend([rel, list(net.find_nodes(["converse", net.checkpath_form(rel)], (n2,))) or None])
        out.append(row)
    return out or None


@define_command("dbassertvirtual", "assert")
def c_dbassertvirtual(net: Any, args: list) -> Any:
    # the virtual relation: a command (such as dbproject or dbjoin) or a
    # Python escape whose value is a list of rows (relation node-set ...)
    virtual = net.eval_arg(args[0]) if isinstance(args[0], list) and _is(args[0][0], "^") \
        else net.topsneval(args[0]).value
    initial = _as_list(args[1]) if len(args) > 1 else []
    result: list = []
    for spec in _as_list(virtual):
        res = net.topsneval(["assert"] + list(initial) + [_quote_ns(x) for x in spec])
        result.extend(_as_list(res.value))
    return tuple(result)


def _quote_ns(x: Any) -> Any:
    return list(x) if isinstance(x, tuple) else x


def _apply_num(net: Any, fn: Any, nsexp: Any) -> tuple:
    ns = net.nseval(nsexp)
    vals = [n.to_number() for n in ns]
    return (net.value_to_node(fn(vals)),)


@define_command("dbmin", ("top", "ns", "bns", "fns"))
def c_dbmin(net: Any, args: list) -> Any:
    return _apply_num(net, min, args[0])


@define_command("dbmax", "dbmin")
def c_dbmax(net: Any, args: list) -> Any:
    return _apply_num(net, max, args[0])


@define_command("dbtot", "dbmin")
def c_dbtot(net: Any, args: list) -> Any:
    return _apply_num(net, sum, args[0])


@define_command("dbcount", "dbmin")
def c_dbcount(net: Any, args: list) -> Any:
    return (net.value_to_node(len(net.nseval(args[0]))),)
