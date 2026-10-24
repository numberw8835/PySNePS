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
"""The demo menu."""

from __future__ import annotations

from typing import Any

SNEPSUL_DEMOS = [
    ("sneps;bidir.sneps", "Node-based bidirectional inference"),
    ("sneps;freeman.sneps", "The Freeman puzzle"),
    ("sneps;jobspuzzle.sneps", "The jobs puzzle"),
    ("sneps;uvbr.sneps", "The unique variable binding rule"),
    ("sneps;numquant;jobspuzzle.sneps", "The jobs puzzle with numerical quantifiers"),
    ("dbms;dbmsdemo.sneps", "SNePS as a relational database"),
    ("sneps;clue.sneps", "Reasoning in the game of Clue (commands written in Python)"),
    ("sneps;sneps79.sneps", "The figures of Shapiro's 1979 SNePS paper"),
]

SNEPSLOG_DEMOS = [
    ("snepslog;socrates.snlog", "All men are mortal"),
    ("snepslog;pegasus.snlog", "Pegasus"),
    ("snepslog;jobspuzzle.snlog", "The jobs puzzle"),
    ("snepslog;steamroller.snlog", "Schubert's steamroller"),
    ("snepslog;ruleintro.snlog", "Rule introduction"),
    ("snepslog;chap4.snlog", "Acting: chapter 4 of the manual (actions written in Python)"),
    ("snepslog;agents.snlog", "An agent that turns to face a direction"),
    ("snebr;autobr.snlog", "Automatic belief revision"),
]


def demo_menu(net: Any, snepslog: bool = False) -> None:
    demos = SNEPSLOG_DEMOS if snepslog else SNEPSUL_DEMOS
    net.write("\nAvailable demonstrations:\n")
    for k, (path, label) in enumerate(demos, 1):
        net.write(f"  {k:2d}:  {label} (sneps:demo;{path})\n")
    net.write("\nUse demo \"sneps:demo;<file>\" to run one.\n")
