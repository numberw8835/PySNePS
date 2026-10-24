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
"""Transcript snapshots of the bundled demos.

The snapshots in tests/snapshots were made with tests/update_snapshots.py.
Those of the demos in ``DEMOS`` match the transcripts of SNePS 2.8 under
CLISP up to case, timing, the installation directory and the changes that
CHANGES.md lists (Python code instead of Lisp code in the dbms and agents
demos, SNePSUL forms written without Lisp quotes); the other demos have
regression snapshots.  A failure here means a change in behaviour.
"""

from __future__ import annotations

import difflib

import pytest

from _demos import ALL_DEMOS, run_demo, snapshot_path


@pytest.mark.parametrize("demo", ALL_DEMOS)
def test_demo_transcript(demo):
    path = snapshot_path(demo)
    if not path.exists():
        pytest.fail(f"no snapshot {path.name}; run python tests/update_snapshots.py {demo}")
    expected = path.read_text(encoding="utf-8")
    actual = run_demo(demo)
    if actual != expected:
        diff = "".join(difflib.unified_diff(expected.splitlines(True), actual.splitlines(True),
                                            "snapshot", "now", n=2))
        pytest.fail(f"{demo} transcript changed:\n{diff[:4000]}")
