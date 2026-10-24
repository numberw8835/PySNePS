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
"""Path-based inference (``sneps/fns/path``, ``sneps/ds/path``).

Paths are written as nested Python lists of strings, mirroring the SNePSUL
syntax: a relation name (``"member-"``), ``"!"``, or a list headed by one of
:data:`PATH_SPECIFIERS`, e.g. ``["compose", "member-", ["kstar", "class"]]``.
A list without a specifier is a composition.

The path follower works on lists of ``(node, flag)`` pairs and also returns
the paths it followed, from which the nodes supporting a path-based
conclusion (the asserted nodes passed through ``!``) are computed.
"""

from __future__ import annotations

from typing import Any

from .network import SNePSError
from .node import Node
from .nodeset import ns_insert, ns_make
from ..util.lists import adjoin, equal

PATH_SPECIFIERS = ("converse", "compose", "kstar", "kplus", "or", "and", "not",
                   "relative-complement", "irreflexive-restrict", "exception",
                   "domain-restrict", "range-restrict")

UNBOUND = object()


def _pair_equal(a: Any, b: Any) -> bool:
    return a[0] is b[0] and a[1] == b[1]


def _path_equal(p1: list, p2: list) -> bool:
    return len(p1) == len(p2) and all(_pair_equal(x, y) for x, y in zip(p1, p2))


class PathMixin:
    """Path definitions and path following, mixed into :class:`~sneps.Network`."""

    match_top_node: Any = UNBOUND
    match_supporting_nodes: Any = UNBOUND

    # ------------------------------------------------------------------
    # predicates
    def is_p(self, p: Any) -> bool:
        return isinstance(p, list) and bool(p) and (
            self.is_r(p[0]) or p[0] in PATH_SPECIFIERS)

    def rel_to_path(self, r: str) -> list:
        return self.pathdefs.get(r) or [r]

    def checkpath(self, path: Any) -> list:
        if self.is_p(path):
            return path
        if self.is_r(path):
            return self.rel_to_path(path)
        raise SNePSError(f" Illegal relation or path: {_pstr(path)}", "find", "checkpath")

    def _path_star(self, items: list) -> bool:
        for curr in items:
            ok = (self.is_r(curr) or curr == "!") if not isinstance(curr, list) \
                else self.legal_def_p(curr)
            if not ok:
                raise SNePSError(f"Incorrect path specification: {_pstr(curr)}", "define-path")
        return True

    def legal_def_p(self, p: Any) -> bool:
        if self.is_r(p) or p == "!":
            return True
        if not isinstance(p, list) or not p:
            return False
        op = p[0]
        if op in ("converse", "kstar", "kplus", "not", "irreflexive-restrict"):
            return len(p) == 2 and self.legal_def_p(p[1])
        if op in ("compose", "or", "and"):
            return self._path_star(p[1:])
        if op in ("relative-complement", "exception"):
            return len(p) == 3 and self.legal_def_p(p[1]) and self.legal_def_p(p[2])
        if op == "domain-restrict":
            return (len(p) == 3 and isinstance(p[1], list) and len(p[1]) == 2
                    and self.legal_def_p(p[1][0]) and not isinstance(p[1][1], list)
                    and self.legal_def_p(p[2]))
        if op == "range-restrict":
            return (len(p) == 3 and isinstance(p[2], list) and len(p[2]) == 2
                    and self.legal_def_p(p[1]) and self.legal_def_p(p[2][0])
                    and not isinstance(p[2][1], list))
        raise SNePSError(f"Illegal path operation: {_pstr(op)}\nIn the specification:  {_pstr(p)}",
                         "Path Syntax Checker", "define-path")

    # ------------------------------------------------------------------
    # defining paths
    def define_path(self, rel: str, path_def: Any) -> None:
        """Define relation REL (and its converse) as implied by PATH_DEF."""
        if not self.legal_def_p(path_def):
            return
        if not isinstance(path_def, list):
            path_def = ["compose", path_def]
        if not self.is_r(rel):
            self.new_r(rel[:-1] if rel.endswith("-") else rel)
        if self.pathdefs.get(rel):
            self.beep()
            self.write(f"\n{rel} already has the path definition: \n\n {_pstr(self.pathdefs[rel])}")
            if self.yes_or_no_p("\nDo you really want to redefine it?"):
                self.undefine_path([rel])
                self._pathlink1(rel, path_def)
                self._pathlink1(self.convt(rel), self.convt_path(path_def))
        else:
            self._pathlink1(rel, path_def)
            self._pathlink1(self.convt(rel), self.convt_path(path_def))

    def yes_or_no_p(self, prompt: str) -> bool:  # overridden by interactive front ends
        return True

    def undefine_path(self, rels: list) -> list:
        for rel in rels:
            if self.is_r(rel):
                self._unlink_path(rel, self.pathdefs.get(rel))
                self.pathdefs.pop(rel, None)
                self.altrels.pop(rel, None)
                c = self.convt(rel)
                self._unlink_path(c, self.pathdefs.get(c))
                self.pathdefs.pop(c, None)
                self.altrels.pop(c, None)
            else:
                self.beep()
                self.write(f"\nWARNING: {rel}  is not a valid relation. \n")
        return rels

    def _unlink_path(self, rel: str, path_def: Any) -> None:
        if path_def is None:
            return
        if isinstance(path_def, list):
            for x in path_def:
                self._unlink_path(rel, x)
        elif self.is_r(path_def):
            self.fwd_paths[path_def] = [x for x in self.fwd_paths.get(path_def, [])
                                        if x[0] != rel]

    def _pathlink1(self, rel: str, path_def: list) -> None:
        self.pathdefs[rel] = path_def
        self.altrels[rel] = self.pathfirstrels(path_def)
        paths = self.pathconnect(path_def)
        for triple in paths:
            self.fwd_paths[triple[0]] = [x for x in self.fwd_paths.get(triple[0], [])
                                         if x[0] != rel]
        temp1: list = []
        for triple in paths:
            old = next((x for x in temp1 if x[0] == triple[0]), None)
            if old is not None:
                rest = old[1:]
                pair = list(triple[1:])
                present = any(equal(pair, rest[i:i + 2]) for i in range(0, len(rest), 2))
                if not present:
                    temp1[temp1.index(old)] = old + list(triple[1:])
            else:
                temp1.insert(0, list(triple))
        for pp in temp1:
            self.fwd_paths[pp[0]] = [[rel] + pp[1:]] + self.fwd_paths.get(pp[0], [])
        self.fresh_line()
        self.write(f"{rel} implied by the path {_pstr(path_def)}\n")

    def pathfirstrels(self, path: Any) -> list:
        if path is None:
            return []
        if not isinstance(path, list):
            return [path]
        op = path[0]
        if op == "converse":
            return self.pathfirstrels(self.convt_path(path[1]))
        if op == "compose":
            return self.pathfirstrels(path[2] if len(path) > 2 and path[1] == "!" else
                                      (path[1] if len(path) > 1 else None))
        if op in ("kstar", "kplus", "relative-complement", "irreflexive-restrict",
                  "exception", "range-restrict"):
            return self.pathfirstrels(path[1])
        if op == "or":
            out: list = []
            for p in path[1:]:
                out.extend(self.pathfirstrels(p))
            return out
        if op == "and":
            lists = []
            for p in path[1:]:
                rels = []
                for r in self.pathfirstrels(p):
                    if r not in rels:
                        rels.append(r)
                lists.append(rels)
            return min(lists, key=len) if lists else []
        if op == "domain-restrict":
            return self.pathfirstrels(path[2])
        return self.pathfirstrels(path[1] if op == "!" and len(path) > 1 else op)

    def pathconnect(self, path: Any) -> list:
        if path == "!":
            return []
        if not isinstance(path, list):
            return [[path, None, path]]
        op = path[0]
        if op == "compose":
            result: list = []
            left: list = []
            comps = path[1:]
            for i, component in enumerate(comps):
                result = result + self._compose_combine(self.pathconnect(component), left, path)
                left = [self.convt_path(component)] + left
            return result
        if op == "converse":
            return self.pathconnect(self.convt_path(path[1]))
        if op in ("kstar", "kplus"):
            return self._k_combine(self.pathconnect(path[1]), path)
        if op in ("or", "and", "irreflexive-restrict"):
            return self._common_combine(path[1:], path)
        if op == "not":
            return []
        if op in ("exception", "relative-complement", "range-restrict"):
            return self._common_combine([path[1]], path)
        if op == "domain-restrict":
            return self._common_combine(path[2:], path)
        return []

    @staticmethod
    def _compose_combine(paths: list, left: list, compose_path: list) -> list:
        out = []
        for x in paths:
            if x[1] is None and not left:
                mid = None
            elif x[1] is None:
                mid = ["compose"] + left if len(left) > 1 else left[0]
            elif not left:
                mid = x[1]
            else:
                mid = ["compose", x[1]] + left
            out.append([x[0], mid, compose_path])
        return out

    def _k_combine(self, paths: list, k_path: list) -> list:
        out = []
        for x in paths:
            conv = self.convt_path(["kstar"] + k_path[1:])
            out.append([x[0], ["compose", x[1], conv] if x[1] else conv, k_path])
        return out

    def _common_combine(self, pathlist: list, path: list) -> list:
        out = []
        for x in pathlist:
            for y in self.pathconnect(x):
                out.append([y[0], y[1], path])
        return out

    def convt(self, r: str) -> Any:
        if r == "!":
            return "!"
        return self.converse(r)

    def convt_path(self, path: Any) -> Any:
        if path is None:
            return None
        if not isinstance(path, list):
            return self.convt(path)
        if len(path) == 1:
            return self.convt(path[0])
        op = path[0]
        if op == "compose":
            return ["compose"] + [self.convt_path(p) for p in reversed(path[1:])]
        if op == "converse":
            return ["converse", self.convt_path(path[1])]
        if op in ("kstar", "kplus"):
            return [op] + [self.convt_path(p) for p in reversed(path[1:])]
        if op in ("or", "and"):
            return [op] + [self.convt_path(p) for p in path[1:]]
        if op == "not":
            return ["not", self.convt_path(path[1])]
        if op in ("relative-complement", "exception"):
            return [op, self.convt_path(path[1]), self.convt_path(path[2])]
        if op == "irreflexive-restrict":
            return ["irreflexive-restrict", self.convt_path(path[1])]
        if op == "domain-restrict":
            return ["range-restrict", self.convt_path(path[2]), [path[1][0], path[1][1]]]
        if op == "range-restrict":
            return ["domain-restrict", [path[2][0], path[2][1]], self.convt_path(path[1])]
        return ["compose"] + [self.convt_path(p) for p in reversed(path)]

    # ------------------------------------------------------------------
    # following paths
    def pathfrom(self, path: list, n: Node) -> tuple:
        """The node set at the end of PATH from node N."""
        if not isinstance(path, list):
            path = [path]
        if len(path) > 1 or self.fwd_paths.get(path[0]):
            top = self.match_top_node
            if top is not UNBOUND:
                if top is n or (isinstance(top, tuple) and len(top) == 1 and top[0] is n):
                    fp = [[(n, True)]]
                else:
                    fp = [[(n, False), (top, True)]]
            else:
                fp = [[(n, True)]]
            result = self._path_infer_1([(n, True)], path, fp)
            if self.match_supporting_nodes is not UNBOUND:
                self.match_supporting_nodes = (
                    [self._retrieve_supporting_nodes(result[1], result[0])]
                    + list(self.match_supporting_nodes))
            return ns_make(x[0] for x in result[0])
        return n.nodeset(path[0])

    def pathto(self, path: list, nbs: list) -> list:
        """The node-bind set of nodes having PATH to the nodes of NBS."""
        path = self.convt_path(path)
        out: list = []
        for nde, bs in nbs:
            newnbs = []
            for node, _status in self._path_infer([(nde, True)], path):
                newnbs.insert(0, (node, bs))
            out = union_nbs(newnbs, out)
        return out

    def _path_infer(self, node: list, path: Any) -> list:
        return self._path_infer_1(node, path, [[(x[0], True)] for x in node])[0]

    def _path_infer_1(self, node: Any, path: Any, followed: list) -> list:
        if not node:
            return [[], []]
        if path is None or path == []:
            return [node, followed]
        if isinstance(node, str):
            return self._path_infer_1([(self.node(node), False)], path, followed)
        if isinstance(node, Node):
            return self._path_infer_1([(node, False)], path, followed)
        if path == "!":
            asserted = self._check_bang(node)
            return [asserted, _assert_and_remove(asserted, followed, node)]
        if not isinstance(path, list):
            result: list = [[], []]
            for one in node:
                if not isinstance(one[0], Node):
                    raise SNePSError("a SNePS node. May be trying to follow a path from a non-node")
                found = _check_link(one[0].nodeset(path), one)
                new_paths: list = []
                if found:
                    new_paths = _add_nodes(found, _select_paths(followed, one[0]))
                result = [_pair_combine(found, result[0]), new_paths + result[1]]
            return result
        if len(path) == 1:
            return self._path_infer_1(node, path[0], followed)
        op = path[0]
        if op == "compose":
            up = self._path_infer_1(node, path[1], followed)
            if len(path) > 2:
                return self._path_infer_1(up[0], ["compose"] + path[2:], up[1])
            return up
        if op == "converse":
            return self._path_infer_1(node, self.convt_path(path[1]), followed)
        if op == "or":
            u: list = [[], []]
            for p in path[1:]:
                res = self._path_infer_1(node, p, followed)
                u = [_pair_combine(u[0], res[0]), u[1] + res[1]]
            return u
        if op == "and":
            acc = self._path_infer_1(node, path[1], followed)
            for p in path[2:]:
                cur = self._path_infer_1(node, p, followed)
                common = _pair_intersctn(cur[0], acc[0])
                common_paths: list = []
                for l in common:
                    common_paths.extend(_path_intersect(_select_paths(acc[1], l[0]),
                                                        _select_paths(cur[1], l[0])))
                acc = [common, common_paths]
            return acc
        if op == "not":
            first = self._path_infer_1(node, path[1], followed)
            reached = [x[0] for x in first[0]]
            l1 = [x for x in self.all_nodes() if not any(x is y for y in reached)]
            flag = not any(not x[1] for x in node)
            return [[(x, flag) for x in l1], first[1]]
        if op == "relative-complement":
            return self._path_infer_1(node, ["and", path[1], ["not", path[2]]], followed)
        if op == "irreflexive-restrict":
            l1 = self._path_infer_1(node, path[1], followed)
            starts = [x[0] for x in node]
            l2 = [x[0] for x in l1[0] if not any(x[0] is s for s in starts)]
            kept = [x for x in l1[0] if any(x[0] is y for y in l2)]
            if not l2:
                return [kept, followed]
            paths: list = []
            for x in l2:
                paths.extend(_select_paths(l1[1], x))
            return [kept, paths]
        if op == "kstar":
            found = list(node)
            sub = path[1]
            found_paths = list(followed)
            while node:
                first_time = self._path_infer_1(node, sub, found_paths)
                temp: list = []
                for pair in first_time[0]:
                    idx = next((i for i, x in enumerate(found) if x[0] is pair[0]), None)
                    if idx is not None:
                        if not pair[1] and found[idx][1] is True:
                            found[idx] = pair
                            temp.insert(0, pair)
                    else:
                        found.insert(0, pair)
                        found_paths = found_paths + _select_paths(first_time[1], pair[0])
                        temp.insert(0, pair)
                node = temp
            return [found, found_paths]
        if op == "kplus":
            first = self._path_infer_1(node, path[1], followed)
            return self._path_infer_1(first[0], ["kstar"] + path[1:], first[1])
        if op == "exception":
            return [self._exception(node, path), []]
        if op == "domain-restrict":
            found_nodes: list = []
            found_paths2: list = []
            z = path[1][1]
            for n in node:
                one = self._path_infer_1([n], path[1][0], followed)
                found_nodes = self._dr_restrict(n, z, one[0]) + found_nodes
                found_paths2 = _put_in_front(_select_paths(one[1], self.node(z)),
                                             (n[0], False)) + found_paths2
            return self._path_infer_1(found_nodes, path[2], found_paths2)
        if op == "range-restrict":
            found_nodes = []
            found_paths2 = []
            z = path[2][1]
            result = self._path_infer_1(node, path[1], followed)
            for n in result[0]:
                one = self._path_infer_1([n], path[2][0], result[1])
                found_nodes = self._dr_restrict(n, z, one[0]) + found_nodes
                found_paths2 = _put_in_front(_select_paths(one[1], self.node(z)),
                                             (n[0], False)) + found_paths2
            return [found_nodes, found_paths2]
        return self._path_infer_1(node, ["compose"] + path, followed)

    def _check_bang(self, node_list: list) -> list:
        return [x for x in node_list if self.isassert(x[0])]

    def _dr_restrict(self, node: tuple, z: Any, node_list: list) -> list:
        zn = self.node(z)
        if zn is None:
            return []
        for x in node_list:
            if x[0] is zn:
                return [(node[0], True)] if x[1] is True else [node]
        return []

    # ------------------------------------------------------------------
    # exception paths (length-path-infer and friends)
    def _exception(self, node: list, path: list) -> list:
        temp1 = self._lpi([(x[0], x[1], 0) for x in node], path[1])
        temp2 = self._lpi([(x[0], x[1], 0) for x in node], path[2])
        result: list = []
        while temp1:
            triple = temp1[0]
            temp1 = temp1[1:]
            l1 = _find_quadruple(triple, triple[0], temp1, temp2)
            temp1 = [x for x in temp1 if x[0] is not triple[0]]
            num, n1, t1, n2, t2 = l1
            pair1 = (triple[0], False)
            pair2 = (triple[0], True)
            if num == 1:
                result.insert(0, pair2)
            elif num in (2, 3):
                result.insert(0, pair1)
            elif num == 4:
                if n2 > n1:
                    result.insert(0, pair1)
            elif num in (5, 10):
                if t2 > n1:
                    result.insert(0, pair1)
            elif num == 6:
                if n2 > t1:
                    result.insert(0, pair2)
            elif num in (7, 11):
                if t2 > t1:
                    result.insert(0, pair2)
            elif num == 8:
                if not n2 <= t1:
                    result.insert(0, pair1 if n1 < n2 else pair2)
            elif num == 9:
                if t2 > t1:
                    result.insert(0, pair1)
            elif num == 12:
                if not t2 <= t1:
                    result.insert(0, pair1 if n1 < n2 else pair2)
        return result

    def _lpi(self, node: list, path: Any) -> list:
        """LENGTH-PATH-INFER: like path following, tracking path lengths."""
        if not node:
            return []
        if path == "!":
            return [x for x in node if self.isassert(x[0])]
        if not isinstance(path, list):
            return _triple_combine(_triple_check_link(node[0][0].nodeset(path), node[0]),
                                   self._lpi(node[1:], path))
        op = path[0]
        if op == "compose":
            if len(path) > 2:
                return self._lpi(self._lpi(node, path[1]), ["compose"] + path[2:])
            return self._lpi(node, path[1])
        if op == "converse":
            return self._lpi(node, self.convt_path(path[1]))
        if op == "or":
            u: list = []
            for p in path[1:]:
                u = _triple_combine(self._lpi(node, p), u)
            return u
        if op == "and":
            return self._lpi_and(node, path)
        if op == "not":
            reached = [x[0] for x in self._lpi(node, path[1])]
            temp = [x for x in self.all_nodes() if not any(x is y for y in reached)]
            flag = not any(not x[1] for x in node)
            return [(x, flag, 0) for x in temp]
        if op == "relative-complement":
            temp = [x[0] for x in self._lpi(node, path[2])]
            return [x for x in self._lpi(node, path[1]) if not any(x[0] is y for y in temp)]
        if op == "irreflexive-restrict":
            temp = [x[0] for x in node]
            return [x for x in self._lpi(node, path[1]) if not any(x[0] is y for y in temp)]
        if op == "kstar":
            return self._lpi_kstar(node, path)
        if op == "kplus":
            return self._lpi(self._lpi(node, path[1]), ["kstar"] + path[1:])
        if op == "exception":
            return [(x[0], x[1], 0) for x in self._exception([(t[0], t[1]) for t in node], path)]
        if op == "domain-restrict":
            result: list = []
            node = list(node)
            while node:
                triple = node[0]
                node = node[1:]
                temp1 = self._lpi([(triple[0], False, 0)], path[1][0])
                if temp1:
                    result = result + _length_dr_restrict(
                        triple[0], _find_quadruple(triple, self.node(path[1][1]), node, temp1))
                node = [x for x in node if x[0] is not triple[0]]
            return self._lpi(result, path[2])
        if op == "range-restrict":
            result = []
            node = self._lpi(node, path[1])
            while node:
                triple = node[0]
                node = node[1:]
                temp1 = self._lpi([(triple[0], False, 0)], path[2][0])
                if temp1:
                    result = result + _length_dr_restrict(
                        triple[0], _find_quadruple(triple, self.node(path[2][1]), node, temp1))
                node = [x for x in node if x[0] is not triple[0]]
            return result
        return self._lpi(node, ["compose"] + path)

    def _lpi_and(self, node: list, path: list) -> list:
        int_list = self._lpi(node, path[1])
        for p in path[2:]:
            if not int_list:
                break
            temp1 = int_list
            temp2 = self._lpi(node, p)
            result: list = []
            while temp1 and temp2:
                head = temp1[0]
                l1 = _find_quadruple(head, head[0], temp1[1:], temp2)
                num, n1, t1, n2, t2 = l1
                z = head[0]
                if num == 4:
                    result.insert(0, (z, False, min(n1, n2)))
                elif num == 5:
                    result.insert(0, (z, True, min(n1, t2)))
                elif num == 6:
                    result.insert(0, (z, True, min(t1, n2)))
                elif num in (7, 9, 11):
                    result.insert(0, (z, True, min(t1, t2)))
                elif num == 8:
                    result.insert(0, (z, False, min(n1, n2)))
                    if t1 < n2:
                        result.insert(0, (z, True, t1))
                elif num == 10:
                    result.insert(0, (z, False, min(n1, n2)))
                    if t2 < n1:
                        result.insert(0, (z, True, t2))
                elif num == 12:
                    result = [(z, False, min(n1, n2)), (z, True, min(t1, t2))] + result
                temp1 = [x for x in temp1[1:] if x[0] is not z]
            int_list = result
        return int_list

    def _lpi_kstar(self, node: list, path: list) -> list:
        found = list(node)
        sub = path[1]
        while node:
            l2 = self._lpi(node, sub)
            found_nodes = [x[0] for x in found]
            new = [x for x in l2 if not any(x[0] is y for y in found_nodes)]
            result: list = []
            temp2: list = []
            while found:
                triple = found[0]
                found = found[1:]
                num, n1, t1, n2, t2 = _find_quadruple(triple, triple[0], found, l2)
                found = [x for x in found if x[0] is not triple[0]]
                z = triple[0]
                fn1 = (z, False, n1) if n1 is not None else None
                ft1 = (z, True, t1) if t1 is not None else None
                fn2 = (z, False, n2) if n2 is not None else None
                ft2 = (z, True, t2) if t2 is not None else None

                def push(x: Any, both: bool = False) -> None:
                    result.insert(0, x)
                    if both:
                        temp2.insert(0, x)
                if num == 1:
                    push(ft1)
                elif num == 2:
                    push(fn1)
                elif num == 3:
                    result[:0] = [fn1, ft1]
                elif num == 4:
                    push(fn2, True) if n2 < n1 else push(fn1)
                elif num == 5:
                    push(ft2, True) if t2 < n1 else push(fn1)
                elif num == 6:
                    push(ft1) if t1 < n2 else push(fn2, True)
                elif num == 7:
                    push(ft2, True) if t2 < t1 else push(ft1)
                elif num == 8:
                    if n2 <= t1:
                        push(fn2, True)
                    else:
                        push(ft1)
                        push(fn2, True) if n2 < n1 else push(fn1)
                elif num == 9:
                    push(ft2, True) if t2 < t1 else push(ft1)
                    push(fn1)
                elif num == 10:
                    if t2 < n1:
                        push(ft2, True)
                        push(fn2, True) if n2 < n1 else push(fn1)
                    else:
                        push(fn1)
                elif num == 11:
                    push(ft2, True) if t2 < t1 else push(ft1)
                    push(fn2, True)
                elif num == 12:
                    if n1 <= t2:
                        result[:0] = [fn1, ft1]
                    else:
                        push(ft2, True) if t2 < t1 else push(ft1)
                        push(fn2, True) if n2 < n1 else push(fn1)
            found = result + new
            node = temp2 + new
        return found

    def _retrieve_supporting_nodes(self, fpaths: list, nodes: list) -> list:
        return _retrieve_supporting_nodes(fpaths, nodes)


# ----------------------------------------------------------------------
# helpers on (node, flag) pairs and followed paths

def _check_link(node_list: tuple, pair: tuple) -> list:
    if not node_list:
        return []
    return [(x, bool(pair[1])) for x in node_list]


def _pair_combine(l1: list, l2: list) -> list:
    l1 = list(l1)
    for pair in l2:
        idx = next((i for i, x in enumerate(l1) if x[0] is pair[0]), None)
        if idx is not None:
            if not pair[1]:
                l1[idx] = pair
        else:
            l1.append(pair)
    return l1


def _pair_intersctn(l1: list, l2: list) -> list:
    out = []
    for x in l1:
        for y in l2:
            if x[0] is y[0]:
                out.append(x if x[1] is True else y)
    return out


def _select_paths(fpaths: list, node: Any) -> list:
    return [fp for fp in fpaths if fp and fp[0][0] is node]


def _add_nodes(nodes: list, fpaths: list) -> list:
    result: list = []
    for node in nodes:
        for path in fpaths:
            result.insert(0, [(node[0], False)] + list(path))
    return result


def _path_intersect(fp1: list, fp2: list) -> list:
    result: list = []
    for p1 in fp1:
        for p2 in fp2:
            result.insert(0, _path_intersect_1(p1, p2))
    return result


def _path_intersect_1(p1: list, p2: list) -> list:
    result = [p1[0]]
    for el2 in p2:
        if not any(_pair_equal(el2, e) for e in p1):
            result.append(el2)
    result.extend(p1[1:])
    return result


def _assert_and_remove(asserted: list, fpaths: list, node: list) -> list:
    result = []
    for fpath in fpaths:
        first = fpath[0][0]
        if any(a[0] is first for a in asserted):
            result.append([(first, True)] + list(fpath[1:]))
        elif not any(x[0] is first for x in node):
            result.append(fpath)
    return result


def _retrieve_supporting_nodes(fpaths: list, nodes: list) -> list:
    all_supports: list = []
    for pair in nodes:
        node = pair[0]
        node_supports: list = []
        for path in fpaths:
            if path and path[0][0] is node:
                support: tuple = ()
                for el in path:
                    if el[1]:
                        support = ns_insert(el[0], support)
                node_supports = adjoin(support, node_supports, equal)
        for support in node_supports:
            all_supports.insert(0, [node, support])
    return all_supports


def _put_in_front(fpaths: list, fpath: tuple) -> list:
    return [[fpath] + list(l) for l in fpaths]


def _triple_check_link(node_list: tuple, triple: tuple) -> list:
    if not node_list:
        return []
    return [(x, triple[1] is True, triple[2] + 1) for x in node_list]


def _triple_combine(l1: list, l2: list) -> list:
    l2 = list(l2)
    for triple in l1:
        z = triple[0]
        if triple[1] is True:
            t2 = next((x for x in l2 if x[0] is z and x[1] is True), None)
            if t2 is not None:
                if triple[2] < t2[2]:
                    l2 = [triple if x is t2 else x for x in l2]
                continue
            n2 = next((x for x in l2 if x[0] is z and not x[1]), None)
            if n2 is not None:
                if triple[2] < n2[2]:
                    l2.insert(0, triple)
            else:
                l2.insert(0, triple)
        else:
            n2 = next((x for x in l2 if x[0] is z and not x[1]), None)
            if n2 is not None:
                if triple[2] < n2[2]:
                    l2 = [triple if x is n2 else x for x in l2]
                    t2 = next((x for x in l2 if x[0] is z and x[1] is True), None)
                    if t2 is not None and triple[2] <= t2[2]:
                        l2 = [x for x in l2 if x is not t2]
                continue
            t2 = next((x for x in l2 if x[0] is z and x[1] is True), None)
            if t2 is not None:
                if triple[2] <= t2[2]:
                    l2 = [triple if x is t2 else x for x in l2]
                else:
                    l2.insert(0, triple)
            else:
                l2.insert(0, triple)
    return l2


def _find_quadruple(triple: tuple, z: Any, l1: list, l2: list) -> tuple:
    if triple[1]:
        t1 = triple[2]
        x = next((x for x in l1 if x[0] is triple[0]), None)
        n1 = x[2] if x is not None else None
    else:
        n1 = triple[2]
        x = next((x for x in l1 if x[0] is triple[0]), None)
        t1 = x[2] if x is not None else None
    x = next((x for x in l2 if x[0] is z and not x[1]), None)
    n2 = x[2] if x is not None else None
    x = next((x for x in l2 if x[0] is z and x[1] is True), None)
    t2 = x[2] if x is not None else None
    key = (n1 is not None, t1 is not None, n2 is not None, t2 is not None)
    table = {(False, True, False, False): 1, (True, False, False, False): 2,
             (True, True, False, False): 3, (True, False, True, False): 4,
             (True, False, False, True): 5, (False, True, True, False): 6,
             (False, True, False, True): 7, (True, True, True, False): 8,
             (True, True, False, True): 9, (True, False, True, True): 10,
             (False, True, True, True): 11}
    return (table.get(key, 12), n1, t1, n2, t2)


def _length_dr_restrict(node: Any, l1: tuple) -> list:
    num = l1[0]
    fn1 = (node, False, l1[1])
    ft1 = (node, True, l1[2])
    if num in (6, 7, 9, 11):
        return [ft1]
    if num in (8, 12):
        return [fn1, ft1]
    if num == 5:
        return [(node, True, l1[1])]
    if num in (4, 10):
        return [fn1]
    return []


# ----------------------------------------------------------------------
# node-bind sets: lists of (node, bindings) with bindings a list of
# (variable-name, node set) pairs

def _bs_equal(bs1: list, bs2: list) -> bool:
    def sub(a: list, b: list) -> bool:
        return all(any(x[0] == y[0] and x[1] == y[1] for y in b) for x in a)
    return sub(bs1, bs2) and sub(bs2, bs1)


def nb_equal(a: tuple, b: tuple) -> bool:
    return a[0] is b[0] and _bs_equal(a[1], b[1])


def union_nbs(nbs1: list, nbs2: list) -> list:
    if not nbs2:
        return list(nbs1)
    return [nb for nb in nbs1 if not any(nb_equal(nb, x) for x in nbs2)] + list(nbs2)


def _pstr(p: Any) -> str:
    """A path as SNePSUL writes it (for messages)."""
    if isinstance(p, list):
        return "(" + " ".join(_pstr(x) for x in p) + ")"
    if p is None:
        return "NIL"
    return str(p)
