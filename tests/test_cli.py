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
"""The command-line entry points (sneps.cli)."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

from sneps import cli

SRC = str(Path(__file__).resolve().parent.parent / "src")


def run(argv, snepslog=False, stdin=""):
    out = io.StringIO()
    code = cli.run(argv, snepslog=snepslog, stdin=io.StringIO(stdin), stdout=out)
    return code, out.getvalue()


def test_sneps_batch_eval(tmp_path):
    save = tmp_path / "kb.json"
    code, out = run(["--batch", "-q", "-e", "(define member class)",
                     "-e", "(assert member Socrates class man)",
                     "-e", "(describe *nodes)", "--save", str(save)])
    assert code == 0
    assert "(M1! (class man) (member Socrates))" in out
    data = json.loads(save.read_text())
    assert [n["name"] for n in data["nodes"] if n["type"] == "mol"] == ["M1"]
    code, out = run(["--batch", "-q", "--restore", str(save),
                     "-e", "(describe (find member Socrates))"])
    assert "(M1! (class man) (member Socrates))" in out


def test_snepslog_reads_stdin():
    code, out = run(["-q"], snepslog=True, stdin="Man(Socrates).\nall(x)(Man(x) => Mortal(x)).\n"
                                                    "Mortal(Socrates)?\n")
    assert code == 0
    assert "wff3!:  Mortal(Socrates)" in out
    assert out.rstrip().endswith("Bye")


def test_snepslog_demo(tmp_path):
    code, out = run(["--batch", "-q", "--demo", "sneps:demo;snepslog;socrates.snlog",
                     "--export", str(tmp_path / "ds")], snepslog=True)
    assert "is now the source of input" in out and "mortal(socrates)" in out.lower()
    assert (tmp_path / "ds" / "metadata.json").exists()


def test_python_m_sneps():
    env = dict(os.environ, PYTHONPATH=SRC + os.pathsep + os.environ.get("PYTHONPATH", ""))
    r = subprocess.run([sys.executable, "-m", "sneps", "--snepslog", "--batch", "-q",
                        "-e", "Man(Socrates)."], capture_output=True, text=True, env=env,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert "wff1!:  Man(Socrates)" in r.stdout
    r = subprocess.run([sys.executable, "-m", "sneps", "--version"], capture_output=True,
                       text=True, env=env, timeout=60)
    assert r.returncode == 0 and r.stdout.startswith("PySNePS")
