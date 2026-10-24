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
"""Input/output: character streams and saving/restoring networks.

:func:`save_network` and :func:`load_network` write and read PySNePS' JSON
network format (:mod:`sneps.io.serialize`), which is also what the SNePSUL
commands ``outnet`` and ``innet`` use.
"""

from __future__ import annotations

import os
from typing import Any


def save_network(net: Any, path: str | os.PathLike) -> None:
    """Save NET to PATH as JSON."""
    from .serialize import save
    save(net, os.fspath(path))


def load_network(net: Any, path: str | os.PathLike) -> Any:
    """Replace the contents of NET by the network saved in PATH."""
    from .serialize import load_into
    path = os.fspath(path)
    with open(path, encoding="utf-8", errors="replace") as fh:
        if not fh.read(256).lstrip().startswith("{"):
            raise ValueError(f"{path} is not a PySNePS network file (JSON)")
    load_into(net, path)
    return net
