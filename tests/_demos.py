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
"""Running the bundled SNePS demos for the transcript snapshot tests.

Each demo is run the way the comparison with SNePS 2.8 under CLISP ran it:
from the demo's directory, with ``demo "<file>" n`` given to a fresh network
that reads names in lower case and whose acting system makes no random
choices.
Transcripts are normalised so that they don't depend on where the package is
installed or on how fast the machine is.
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path

import sneps
from sneps import Network
from sneps.io.streams import InputStream, OutputStream

DEMO_DIR = Path(sneps.__file__).resolve().parent / "data" / "demo"
SNAPSHOT_DIR = Path(__file__).resolve().parent / "snapshots"

# The demos whose transcripts are those of SNePS 2.8 under CLISP (apart from
# the changes listed in CHANGES.md).
DEMOS = [
    "sneps/bidir.sneps",
    "dbms/dbmsdemo.sneps",
    "sneps/freeman.sneps",
    "sneps/jobspuzzle.sneps",
    "sneps/numquant/jobspuzzle.sneps",
    "sneps/numquant/meeting.sneps",
    "sneps/numquant/mother.sneps",
    "sneps/numquant/owner.sneps",
    "sneps/uvbr.sneps",
    "snepslog/pegasus.sneps",
    "snepslog/agents.snlog",
    "snepslog/blackbeard3.snlog",
    "snepslog/example1.snlog",
    "snepslog/example2.snlog",
    "snepslog/example3.snlog",
    "snepslog/example4.snlog",
    "snepslog/example5.snlog",
    "snepslog/freeman.snlog",
    "snepslog/jobspuzzle.snlog",
    "snepslog/meetings.snlog",
    "snepslog/pegasus.snlog",
    "snepslog/ruleintro.snlog",
    "snepslog/socrates.snlog",
    "snepslog/sourcedMeetings.snlog",
    "snepslog/steamroller.snlog",
    "snepslog/theorems.snlog",
    "snepslog/uvbr.snlog",
    "defaults/yale-shooting.snlog",
]

# Regression snapshots of the other demos.  Their transcripts differ from
# those of SNePS 2.8 under CLISP in the ways CHANGES.md explains (chap4,
# duck, autobr, clue and sneps79 had their Lisp code rewritten in Python).
OTHER_DEMOS = [
    "snepslog/chap4.snlog",
    "snepslog/duck.snlog",
    "snepslog/blackbeard1.snlog",
    "snepslog/blackbeard2.snlog",
    "snebr/autobr.snlog",
    "sneps/clue.sneps",
    "sneps/sneps79.sneps",
    "sneps/like.sneps",
    "defaults/birds.sneps",
    "defaults/yale-shooting.sneps",
]

ALL_DEMOS = DEMOS + OTHER_DEMOS


def snapshot_path(demo: str) -> Path:
    return SNAPSHOT_DIR / (demo.replace("/", "_") + ".txt")


def normalize(text: str) -> str:
    text = text.replace(str(DEMO_DIR), "$DEMO")
    return re.sub(r"CPU time : [0-9.]+", "CPU time : #.##", text)


def run_demo(demo: str) -> str:
    """The normalised transcript of running DEMO (a path relative to DEMO_DIR)."""
    path = DEMO_DIR / demo
    buf = io.StringIO()
    net = Network(output=OutputStream(buf))
    net.choose_randomly = False
    net.fold_case = "lower"
    cwd = os.getcwd()
    os.chdir(path.parent)
    try:
        if demo.endswith(".snlog"):
            net.snepslog_repl(inunit=InputStream(text=f'demo "{path}" n\nexit\n'), hello=False)
        else:
            net.sneps(inunit=InputStream(text=f'(demo "{path}" n)\n(exit)\n'), banner=False)
    finally:
        os.chdir(cwd)
    return normalize(buf.getvalue())
