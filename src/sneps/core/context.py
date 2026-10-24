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
"""Contexts (``sneps/ds/context0`` ... ``context3``).

A context is a set of hypotheses (asserted nodes).  Contexts are shared:
there is at most one context per hypothesis set, and each may be known by
several names (SNePS variables whose value is the context).
"""

from __future__ import annotations


class Context:
    __slots__ = ("order", "names", "hyps", "kinconsistent", "okinconsistent", "__weakref__")

    def __init__(self, order: int, hyps: tuple):
        self.order = order
        self.names: tuple = ()      # svar names, most recently added first
        self.hyps = hyps            # node set
        self.kinconsistent = False  # known to be inconsistent
        self.okinconsistent = False  # inconsistency accepted by the user

    def __repr__(self) -> str:
        return f"C{self.order}"

    __str__ = __repr__
