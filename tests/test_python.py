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
"""Python as SNePS's host language: the SNePSUL reader and printer, the ``^``
and ``^^`` escapes, primitive actions and commands written in Python, and a
check that no Lisp is left in the package."""

from __future__ import annotations

import io
from fractions import Fraction
from pathlib import Path

import pytest

import sneps
from sneps import Network, SNePSError, cli
from sneps.core.printing import Binding, Text, escape_name, flat_text
from sneps.io.streams import InputStream, OutputStream
from sneps.snepsul.reader import PythonCode, ReaderError, read_all

PACKAGE = Path(sneps.__file__).resolve().parent


def transcript(net: Network) -> str:
    return net.outunit.getvalue()


def quiet_net() -> Network:
    return Network(output=OutputStream(io.StringIO()))


# ----------------------------------------------------------------------
# reading and writing SNePSUL

def test_reader_produces_plain_python_data():
    forms = read_all('(assert member Socrates class man) (build forall $x ant (build arg *x)) '
                     '(find member ?who) (= a b) #b ; a comment\n'
                     '#| a block comment |# (|police officer| "text" 12 1/2 2.5 nil t :context)')
    assert forms[0] == ["assert", "member", "Socrates", "class", "man"]
    assert forms[1] == ["build", "forall", ["$", "x"], "ant", ["build", "arg", ["*", "x"]]]
    assert forms[2] == ["find", "member", ["?", "who"]]
    assert forms[3] == ["=", "a", "b"]
    assert forms[4] == ["#", "b"]
    last = forms[5]
    assert last[:2] == ["police officer", "text"] and isinstance(last[1], Text)
    assert last[2:] == [12, Fraction(1, 2), 2.5, None, True, ":context"]


def test_reader_python_escapes():
    form = read_all('(build lex ^(name.upper()) arg (^ f(")", [1, 2])))')[0]
    assert form[:2] == ["build", "lex"]
    assert isinstance(form[2][1], PythonCode) and form[2][1].source == "(name.upper())"
    assert form[4][0] == "^" and form[4][1].source == 'f(")", [1, 2])'
    top = read_all("^ x = 1\n(foo)")
    assert top[0][1].source == "x = 1" and top[1] == ["foo"]
    with pytest.raises(ReaderError):
        read_all("(unfinished")


def test_printer_escapes_names_and_abbreviates():
    assert escape_name("0") == "|0|" and escape_name("police officer") == "|police officer|"
    assert escape_name("Socrates") == "Socrates"
    assert flat_text(["build", "forall", [["$", "x"]], "arg", ["*", "x"]], True) == \
        "(build forall ($x) arg *x)"
    assert flat_text([Text("a b"), "a b", None, True, Binding("x", "y")], True) == \
        '("a b" |a b| nil t (x . y))'


# ----------------------------------------------------------------------
# the escapes

def test_snepslog_escapes_and_python_primitive_actions():
    net = quiet_net()
    net.snepslog_repl(inunit=InputStream(text="""set-mode-3
define-frame say(action object1)
^ 6 * 7
^^
said = []

@primaction
def say(object1):
    said.append(object1[0].name)

attach_primaction("say", say)
^^
perform say(Hello)
^ said
exit
"""), hello=False)
    out = transcript(net)
    assert "\n42\n" in out and "['Hello']" in out
    assert net.python.namespace["said"] == ["Hello"]


def test_snepsul_escapes_and_python_commands():
    net = quiet_net()
    net.run_snepsul("""(define member class)
        (assert member ^(net.fold_name("Socrates")) class man)
        ^^""")
    host = net.python
    host.run('''
@command
def isa(x, y):
    return snepsul("(assert member {} class {})", x, y)
''')
    assert net.run_snepsul("(^ 1 + 2)") == 3
    assert [n.name for n in net.run_snepsul("(isa Plato man)")] == ["M2"]
    assert sorted(n.name for n in net.run_snepsul("(find member- (find class man))")) == \
        ["Plato", "Socrates"]
    # snepsul() runs any command, and raises SNePS errors in Python
    assert host.evaluate('snepsul("(build member Zeus class god)")')[0].is_mol
    with pytest.raises(SNePSError):
        host.evaluate('snepsul("(build nosuchrelation x)")')


def test_python_errors_are_reported_not_raised():
    net = quiet_net()
    net.python.run("1 / 0")
    assert "ZeroDivisionError" in transcript(net)
    net.python.run("def broken(:")
    assert "SyntaxError" in transcript(net)


def test_tell_with_arguments_and_python_orders():
    net = Network(output=False)
    m = net.tell("Man({}).", "Socrates")[0]
    net.tell("all(x)(Man(x) => Mortal(x)).")
    assert net.ask("Mortal(Socrates)")
    assert net.tell("{}!", m)                       # a node stands for its wff name
    net.python.run("def any_order(p, q):\n    return True")
    net.tell("set-order any_order")
    assert net.br_totalorder(net, m, m) is True


def test_load_python_file(tmp_path):
    actions = tmp_path / "actions.py"
    actions.write_text("@primaction\ndef shout(object1):\n    print(object1[0].name.upper())\n")
    out = io.StringIO()
    cli.run(["--batch", "-q", "--load", str(actions), "-e", "set-mode-3",
             "-e", "define-frame shout(action object1)", "-e", "^ attach_primaction('shout')",
             "-e", "perform shout(hello)"], snepslog=True, stdin=io.StringIO(), stdout=out)
    assert "HELLO" in out.getvalue()


# ----------------------------------------------------------------------
# no Lisp

def test_no_lisp_left_in_the_package():
    sources = [p for p in PACKAGE.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    assert not [p for p in sources if p.suffix in (".lisp", ".lsp", ".cl")]
    assert not (PACKAGE / "lisp").exists()
    mentions = [str(p.relative_to(PACKAGE)) for p in sources
                if p.suffix in (".py", ".sneps", ".snlog") and "lisp" in p.read_text().lower()]
    assert mentions == []
