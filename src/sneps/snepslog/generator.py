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
"""Rendering nodes as SNePSLOG text (``snepslog/generator/generator.atn``,
``generator`` and ``printer``).

The SNePS distribution generates SNePSLOG with an ATN grammar; this module
implements the same generation network as Python functions.  As in SNePS,
the text generated for a node is cached in the node (``node.snepslog``) and
reused afterwards.
"""

from __future__ import annotations

from typing import Any, Optional

from ..core.node import Node
from ..core.printing import escape_name

FAIL = None
VERSION = "snepslog-version"
PARTIAL = "snepslog-partial-description"
COMPLETE = "snepslog-complete-description"


def flistify(x: Any) -> list:
    return list(x) if isinstance(x, list) else [x]


def make_tuple(items: list, sep: str, open_: str, close: str) -> list:
    out: list = [open_]
    for k, item in enumerate(items):
        out.extend(flistify(item))
        if k < len(items) - 1:
            out.append(sep)
    out.append(close)
    return out


def m_to_wff(node: Node) -> str:
    if node.is_mol:
        return "wff" + node.name[1:]
    return node.name.strip("!")


class Generator:
    """SNePSLOG generation for one network."""

    def __init__(self, net: Any):
        self.net = net

    # -- the snepslog cache -------------------------------------------------
    @staticmethod
    def get_version(x: Any) -> Any:
        if isinstance(x, Node):
            sn = x.snepslog
            if isinstance(sn, dict):
                return sn.get(VERSION)
            return sn
        return x

    @staticmethod
    def set_version(node: Node, version: Any) -> Any:
        node.snepslog = {VERSION: version}
        return version

    @staticmethod
    def get_complete(node: Node, state: str) -> Any:
        sn = node.snepslog
        if node.is_var:
            return sn
        return sn.get(state) if isinstance(sn, dict) else None

    @staticmethod
    def set_complete(node: Node, version: Any, state: str) -> Any:
        sn = node.snepslog if isinstance(node.snepslog, dict) else {}
        sn = dict(sn)
        sn[state] = version
        node.snepslog = sn
        return version

    # -- predicates (generator) ----------------------------------------
    def _num(self, node: Any) -> Any:
        if not isinstance(node, Node):
            return None
        v = node.value
        return v

    def quantified_p(self, n: Node, quantified: bool) -> bool:
        return not quantified and bool(n.nodeset("forall") or n.nodeset("exists")
                                       or n.nodeset("pevb"))

    def relation_p(self, n: Any, quantified: bool = False) -> bool:
        return (isinstance(n, Node) and not self.quantified_p(n, quantified)
                and bool(self.net.relation_predicate(n)))

    def connected_p(self, n: Node, quantified: bool = False) -> bool:
        return not self.quantified_p(n, quantified) and bool(n.nodeset("cq") or n.nodeset("arg"))

    @staticmethod
    def atomic_p(n: Any) -> bool:
        return isinstance(n, Node) and n.is_base

    def entailment_p(self, n: Node) -> bool:
        return bool(n.nodeset("cq"))

    def thresh_p(self, n: Node, quantified: bool = False) -> bool:
        return not self.quantified_p(n, quantified) and (self.general_thresh_p(n)
                                                        or self.equivalence_p(n))

    def equivalence_p(self, n: Node) -> bool:
        t = n.nodeset("thresh")
        return bool(t) and self._num(t[0]) == 1

    def general_thresh_p(self, n: Node) -> bool:
        t = n.nodeset("thresh")
        return bool(t) and self._num(t[0]) != 1

    def or_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        return (bool(mn) and self._num(mn[0]) == 1 and bool(mx)
                and len(n.nodeset("arg")) == self._num(mx[0]))

    def and_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        return (bool(mn) and bool(mx) and mn[0] is mx[0]
                and len(n.nodeset("arg")) == self._num(mx[0]))

    def not_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        return (bool(mn) and self._num(mn[0]) == 0 and bool(mx) and self._num(mx[0]) == 0
                and len(n.nodeset("arg")) == 1)

    def nor_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        return (bool(mn) and self._num(mn[0]) == 0 and bool(mx) and self._num(mx[0]) == 0
                and len(n.nodeset("arg")) > 1)

    def nand_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        args = n.nodeset("arg")
        return (bool(mn) and self._num(mn[0]) == 0 and len(args) > 1 and bool(mx)
                and self._num(mx[0]) == len(args) - 1)

    def xor_p(self, n: Node) -> bool:
        mn, mx = n.nodeset("min"), n.nodeset("max")
        return (bool(mn) and self._num(mn[0]) == 1 and bool(mx) and self._num(mx[0]) == 1
                and len(n.nodeset("arg")) > 1)

    def higher_priority(self, n: Node, operation: str) -> bool:
        ops = ["entailment", "thresh", "or", "and", "not"]
        fns = {"entailment": self.entailment_p, "thresh": self.thresh_p, "or": self.or_p,
               "and": self.and_p, "not": self.not_p}
        return any(fns[o](n) for o in ops[ops.index(operation):])

    # -- the generation network -----------------------------------------------
    def gen(self, x: Any, quantified: bool = False) -> Any:
        v = self.get_version(x)
        if v is not None and v != [] and v != ():
            return v
        if not isinstance(x, Node):
            return FAIL
        if x.is_base:
            return self.set_version(x, escape_name(x.name))
        if self.relation_p(x, quantified):
            return self.g_relation(x)
        if self.connected_p(x, quantified):
            return self.g_connected(x, quantified)
        if self.quantified_p(x, quantified):
            return self.g_quantified(x)
        return FAIL

    def _gen_list(self, nodes: Any) -> Optional[list]:
        out = []
        for n in nodes or ():
            e = self.gen(n)
            if e is FAIL:
                return None
            out.append(e)
        return out

    def g_list_of_expressions(self, nodes: Any, sep: str, open_: str, close: str) -> Any:
        items = self._gen_list(nodes)
        if items is None:
            return FAIL
        return make_tuple(items, sep, open_, close)

    def g_relation(self, node: Node) -> Any:
        pred = self.net.relation_predicate(node)
        target = pred[0] if isinstance(pred, (tuple, list)) else pred
        relation = self.gen(target)
        if relation is FAIL:
            return FAIL
        args = []
        for item in self.net.relation_argument_list(node):
            if isinstance(item, (tuple, list)) and len(item) > 1:
                e = self.g_list_of_expressions(item, ",", "{", "}")
            else:
                first = item[0] if isinstance(item, (tuple, list)) and item else (
                    None if isinstance(item, (tuple, list)) else item)
                e = self.gen(first) if first is not None else FAIL
            if e is FAIL:
                return FAIL
            args.append(e)
        result = [relation] + make_tuple(args, ",", "(", ")") if not isinstance(relation, list) \
            else [relation] + make_tuple(args, ",", "(", ")")
        return self.set_version(node, result)

    def g_connected(self, node: Node, quantified: bool) -> Any:
        if self.entailment_p(node):
            return self.g_entailment(node, quantified)
        if self.thresh_p(node, quantified):
            if self.general_thresh_p(node):
                return self.g_threshi(node)
            if self.equivalence_p(node):
                return self.g_arguments(node, node.nodeset("arg"), "thresh", " <=> ", "", "")
            return FAIL
        if node.nodeset("min"):
            return self.g_andor(node, quantified)
        return FAIL

    def g_entailment(self, node: Node, quantified: bool) -> Any:
        if len(node.nodeset("ant")) == 1 and len(node.nodeset("cq")) == 1:
            return self.g_simple_entailment(node, quantified)
        if node.nodeset("ant"):
            ants = self.g_list_of_expressions(node.nodeset("ant"), ",", "{", "}")
            impl = " v=> "
        elif node.nodeset("&ant") and node.nodeset("thresh"):
            ants = self.g_list_of_expressions(node.nodeset("&ant"), ",", "{", "}")
            impl = f" {node.nodeset('thresh')[0]}=> "
        elif node.nodeset("&ant"):
            ants = self.g_list_of_expressions(node.nodeset("&ant"), ",", "{", "}")
            impl = " &=> "
        else:
            return FAIL
        if ants is FAIL:
            return FAIL
        cqs = self.g_list_of_expressions(node.nodeset("cq"), ",", "{", "}")
        if cqs is FAIL:
            return FAIL
        return self.set_version(node, list(ants) + [impl] + list(cqs))

    def _paren_unless_simple(self, n: Node, expr: Any, quantified: bool) -> list:
        if self.relation_p(n, quantified) or self.atomic_p(n):
            return flistify(expr)
        return ["("] + flistify(expr) + [")"]

    def g_simple_entailment(self, node: Node, quantified: bool) -> Any:
        ant = node.nodeset("ant")[0]
        cq = node.nodeset("cq")[0]
        a = self.gen(ant)
        if a is FAIL:
            return FAIL
        c = self.gen(cq)
        if c is FAIL:
            return FAIL
        result = (self._paren_unless_simple(ant, a, quantified) + [" => "]
                  + self._paren_unless_simple(cq, c, quantified))
        return self.set_version(node, result)

    def g_threshi(self, node: Node) -> Any:
        args = self.g_list_of_expressions(node.nodeset("arg"), ",", "{", "}")
        if not args:
            return FAIL
        if node.nodeset("threshmax"):
            v = (["thresh", "("] + list(node.nodeset("thresh")) + [","]
                 + list(node.nodeset("threshmax")) + [")"] + args)
        else:
            v = ["thresh", "("] + list(node.nodeset("thresh")) + [")"] + args
        return self.set_version(node, v)

    def g_arguments(self, node: Node, items: Any, operation: str, sep: str, open_: str,
                    close: str) -> Any:
        out = []
        for n in items:
            e = self.gen(n)
            if e is FAIL:
                return FAIL
            if self.higher_priority(n, operation):
                e = ["("] + flistify(e) + [")"]
            out.append(e)
        return self.set_version(node, make_tuple(out, sep, open_, close))

    def g_andor(self, node: Node, quantified: bool) -> Any:
        args = node.nodeset("arg")
        if self.not_p(node):
            r = self.gen(args[0])
            if r is FAIL:
                return FAIL
            if self.relation_p(args[0]) or self.atomic_p(args[0]):
                v = ["~"] + flistify(r)
            else:
                v = ["~("] + flistify(r) + [")"]
            return self.set_version(node, v)
        if self.and_p(node):
            out = []
            for n in args:
                e = self.gen(n)
                if e is FAIL:
                    return FAIL
                if self.entailment_p(n) or self.thresh_p(n) or self.or_p(n):
                    e = ["("] + flistify(e) + [")"]
                out.append(e)
            return self.set_version(node, make_tuple(out, " and ", "", ""))
        if self.or_p(node):
            v = self.g_list_of_expressions(args, " or ", "", "")
            return FAIL if v is FAIL else self.set_version(node, v)
        for pred, word in ((self.nor_p, "nor"), (self.xor_p, "xor"), (self.nand_p, "nand")):
            if pred(node):
                v = self.g_list_of_expressions(args, ",", "{", "}")
                return FAIL if v is FAIL else self.set_version(node, [word] + v)
        v = self.g_list_of_expressions(args, ",", "{", "}")
        if v is FAIL:
            return FAIL
        params = make_tuple([list(node.nodeset("min")), list(node.nodeset("max"))], ",", "(", ")")
        return self.set_version(node, ["andor"] + params + v)

    def g_quantified(self, node: Node) -> Any:
        if node.nodeset("forall"):
            return self._g_quant(node, "forall", "all")
        if node.nodeset("exists"):
            return self._g_quant(node, "exists", "exists")
        if node.nodeset("pevb"):
            return self.g_num_quant(node)
        return FAIL

    def _g_quant(self, node: Node, rel: str, word: str) -> Any:
        variables = self.g_list_of_expressions(node.nodeset(rel), ",", "(", ")")
        if variables is FAIL:
            return FAIL
        args = node.nodeset("arg")
        mn, mx = node.nodeset("min"), node.nodeset("max")
        if (len(args) == 1 and mn and mn[0].name == "1" and mx and mx[0].name == "1"):
            q = self.gen(args[0])
        else:
            q = self.gen(node, quantified=True)
        if q is FAIL or not q:
            return FAIL
        return self.set_version(node, [word] + list(variables) + ["("] + flistify(q) + [")"])

    def g_num_quant(self, node: Node) -> Any:
        variables = self.g_list_of_expressions(node.nodeset("pevb"), ",", "(", ")")
        ants = self.g_list_of_expressions(node.nodeset("&ant"), ",", "{", "}")
        cqs = self.g_list_of_expressions(node.nodeset("cq"), ",", "{", "}")
        if variables is FAIL or ants is FAIL or cqs is FAIL:
            return FAIL

        def p(r: str) -> Any:
            ns = node.nodeset(r)
            return ns[0] if ns else "_"
        params = make_tuple([p("emin"), p("emax"), p("etot")], ",", "(", ")")
        return self.set_version(node, ["nexists"] + params + list(variables) + ["["] + list(ants)
                                + [":"] + list(cqs) + ["]"])

    # -- descriptions (the generate-snepslog-description states) --------------
    def derivation_histories(self, node: Node) -> list:
        hist = []
        for ot, cts in node.asupport:
            for ct in cts:
                wffs = [m_to_wff(h) for h in reversed(ct.hyps)]
                hist.insert(0, make_tuple([ot, make_tuple(wffs, ",", "{", "}")], ",", "<", ">"))
        return make_tuple(hist, ",", "{", "}")


def printer(tokens: Any) -> str:
    """PRINTER: join the generated tokens into a string."""
    if tokens is None:
        return ""
    out = []
    for t in flistify(tokens):
        if callable(t):
            out.append(printer(t()))
        elif isinstance(t, list):
            out.append(printer(t))
        else:
            out.append(str(t))
    return "".join(out)
