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
"""Regenerate the demo transcript snapshots in tests/snapshots.

Run this after a change that is meant to alter demo transcripts, and check
the differences (``git diff tests/snapshots``) before committing them.
Usage: python tests/update_snapshots.py [demo ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _demos import ALL_DEMOS, SNAPSHOT_DIR, run_demo, snapshot_path  # noqa: E402


def main(argv: list[str]) -> int:
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    for demo in argv or ALL_DEMOS:
        text = run_demo(demo)
        path = snapshot_path(demo)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        path.write_text(text, encoding="utf-8")
        status = "new" if old is None else ("unchanged" if old == text else "CHANGED")
        print(f"{status:9} {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
