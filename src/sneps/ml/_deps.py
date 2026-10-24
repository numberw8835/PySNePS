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
"""Lazy imports of the optional machine-learning dependencies."""

from __future__ import annotations

import importlib
from typing import Any

_EXTRAS = {"torch": "torch"}


def require(module: str, feature: str) -> Any:
    """Import MODULE, or explain how to install it if FEATURE needs it."""
    try:
        return importlib.import_module(module)
    except ImportError as e:
        top = module.split(".")[0]
        extra = _EXTRAS.get(top, "ml")
        raise ImportError(
            f"{feature} needs the optional dependency '{top}'; install it with "
            f"`pip install pysneps[{extra}]` (or `pip install {top}`)") from e
