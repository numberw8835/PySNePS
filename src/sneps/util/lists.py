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
"""List operations with the element order SNePS depends on.

The order in which SNePS processes reports and requests determines the
order in which inferred nodes are created and named, so set operations on
lists must keep a definite order.  These are the orders of the original
SNePS 2.8, against which this translation was checked.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Any, Callable, Sequence

_NUMBER_TYPES = (int, float, Fraction, complex)


def same(a: Any, b: Any) -> bool:
    """Identity, or equal numbers of the same type, or equal strings."""
    if a is b:
        return True
    ta = type(a)
    return ta is type(b) and (ta in _NUMBER_TYPES or ta is str) and a == b


def equal(a: Any, b: Any) -> bool:
    """Structural equality: sequences element by element, atoms with :func:`same`."""
    if a is b:
        return True
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return same(a, b)


def union(l1: Sequence, l2: Sequence, test: Callable[[Any, Any], bool] = same) -> list:
    """The elements of L1 that are not in L2, followed by all of L2."""
    if not l1:
        return list(l2)
    if not l2:
        return list(l1)
    return [x for x in l1 if not any(test(x, y) for y in l2)] + list(l2)


def adjoin(item: Any, seq: Sequence, test: Callable[[Any, Any], bool] = same) -> list:
    """SEQ with ITEM in front, unless it is already a member."""
    if any(test(item, x) for x in seq):
        return list(seq)
    return [item] + list(seq)
