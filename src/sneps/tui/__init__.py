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
"""A full-screen terminal interface to SNePS.

``run_tui(net, mode)`` opens it; the ``sneps``/``snepslog`` commands and
``python -m sneps`` start it when they run in a terminal (``--classic`` gives
the plain read-eval-print loops).  It needs the optional ``prompt_toolkit``
package (``pip install pysneps[tui]``).
"""

from __future__ import annotations

from typing import Any, Iterable


def available() -> bool:
    """True if prompt_toolkit, which the interface needs, can be imported."""
    import importlib.util
    return importlib.util.find_spec("prompt_toolkit") is not None


def run_tui(net: Any = None, mode: str = "snepslog", commands: Iterable[str] = (),
            welcome: bool = True) -> Any:
    """Open the interface on NET (a new network if None) talking MODE
    ("snepslog" or "sneps"), first sending COMMANDS; returns the network."""
    from .app import run_tui as _run
    return _run(net, mode, commands, welcome)


__all__ = ["available", "run_tui"]
