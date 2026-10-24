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
"""The public :class:`Network` class."""

from __future__ import annotations

from typing import Any, Optional

from .core.build import BuildMixin
from .core.describe import DescribeMixin
from .core.erase import EraseMixin
from .core.network import NetworkBase
from .core.paths import PathMixin
from .io.streams import NullOutputStream
from .match.unify import MatchMixin
from .ml import MLMixin
from .snebr import BRMixin, null_order
from .snepsul import commands as _commands  # noqa: F401  (registers the commands)
from .snepsul.evaluator import SnepsulMixin
from .snepslog.session import SnepslogMixin
from .snip.acting import ActingMixin
from .snip.engine import SnipMixin
from .snip.handlers import RuleHandlersMixin
from .snip.multi import MultiMixin


class Network(MLMixin, SnepslogMixin, SnepsulMixin, BRMixin, ActingMixin,
              RuleHandlersMixin, SnipMixin, MultiMixin, MatchMixin, DescribeMixin,
              EraseMixin, BuildMixin, PathMixin, NetworkBase):
    def __init__(self, output: Optional[Any] = None):
        NetworkBase.__init__(self, output)
        self._init_snip()
        self._init_acting()
        self._init_snebr()
        self._init_snepsul()
        self.br_orders = {"null-order": null_order}
        self._init_snepslog()
        out = self.outunit
        self.outunit = NullOutputStream()
        self.resetnet(True)
        self.outunit = out

    def addsupport(self, sup: tuple, n: Any) -> None:
        from .snip.structs import sup_merge
        n.asupport = sup_merge(sup, n.asupport)
