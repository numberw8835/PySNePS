# PySNePS

**SNePS 2 rewritten in Python, without the natural-language part.**

PySNePS is a rewrite of **SNePS 2** (version 2.8) in Python.  SNePS, the
Semantic Network Processing System, was created by Stuart C. Shapiro and the
SNePS Research Group at the University at Buffalo.  It is a knowledge
representation and reasoning system: every proposition, rule and act is a
node of a propositional semantic network, and SNePS reasons with these
nodes, keeps track of what each belief depends on, revises its beliefs when
they contradict each other, and carries out acts.

PySNePS contains all of SNePS 2 except its natural-language segment (SNaLPS:
the English morphology, the lexicons and the GATN parser and generator).  It
is pure Python: there is no Lisp underneath, and where SNePS used to escape
to Lisp, it escapes to Python.  It is also an ordinary, importable Python
package: `import sneps` gives you knowledge bases that you can use from your
own programs and notebooks.

PySNePS was made as **a help for students** who want to learn and use SNePS:
it runs wherever Python runs, needs no Lisp system, comes with a terminal
interface that has help for every mode, and includes the demos of the SNePS
distribution.

PySNePS is **free and open source**: anyone may use, study, change and share
it, under the same license as SNePS (the University at Buffalo Public
License).  **SNePS belongs to its original authors**: all rights in SNePS
are reserved by them and by the Research Foundation of State University of
New York, on behalf of University at Buffalo.  The translation to Python is
by numberw8835.  See [Credits, rights and license](#credits-rights-and-license).

* [What is included](#what-is-included)
* [Setting it up](#setting-it-up)
* [How to use it](#how-to-use-it)
* [How faithful it is](#how-faithful-it-is)
* [For developers](#for-developers)
* [Credits, rights and license](#credits-rights-and-license)

## What is included

* **SNePSLOG**, the logic interface, in its three modes (mode 3 with
  user-defined case frames);
* **SNePSUL**, the SNePS User Language, for building, finding and describing
  nodes, defining relations and paths, and managing contexts;
* **SNIP**, the inference package: entailment, or-entailment, and-or, thresh,
  numerical entailment and quantifiers, path-based inference, forward and
  backward inference scheduled by the MULTI process system, and rule
  introduction;
* **SNeRE**, the acting system: primitive and mental acts, control acts
  (`snsequence`, `snif`, `sniterate`, `do-all`, `do-one`, `withsome`,
  `withall`, `achieve`), plans, goals, preconditions, effects and policies
  (`whendo`, `wheneverdo`);
* **SNeBR**, belief revision with assumption-based contexts, nogoods, and
  automatic or interactive choice of the beliefs to give up;
* the demos of the SNePS 2.8 distribution;
* a full-screen terminal interface with help for every mode, and the classic
  read-eval-print loops;
* exports of a knowledge base for machine learning (graphs, triples, tensors,
  datasets).

Not included: the natural-language tools (SNaLPS) and the demos that need
them, the graphical interfaces of SNePS (XGinseng, Garnet, SnepsGUI) and its
Java and Lisp interfaces.  Python takes the place of Lisp: primitive actions,
new commands and the `^`/`^^` escapes are written in Python.

## Setting it up

You need **Python 3.10 or later** and a terminal.  Check your Python with
`python3 --version` (on Windows: `python --version`).  The only other
package PySNePS needs, prompt_toolkit (for the terminal interface), is
installed with it.

### 1. Get PySNePS

Copy or download the PySNePS folder, and open a terminal in it (the folder
that contains `pyproject.toml`).

### 2. Install it

A virtual environment keeps PySNePS and its dependencies apart from the rest
of your system.  On Linux and macOS:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

On Windows:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

`pip install -e .` installs PySNePS "editable": the package is used straight
from the folder, so changes to the sources take effect at once.  Use
`pip install .` for a normal installation.  Activate the environment again
(the `activate` line) in every new terminal before you use PySNePS.

### 3. Check that it works

```sh
snepslog --version                                     # PySNePS 2.8.0.dev1
snepslog --batch --demo "sneps:demo;snepslog;socrates.snlog"
python -c "import sneps; print(sneps.Network)"
```

The second command runs the first demo: SNePS learns that all men are
mortal and concludes that Socrates is.

### Optional extras

```sh
pip install -e ".[ml]"      # numpy, scipy and networkx, for the machine-learning exports
pip install -e ".[torch]"   # torch, for tensor exports to PyTorch
pip install -e ".[dev]"     # pytest, to run the test suite
```

### Without installing

From the folder itself, without any installation (prompt_toolkit must be
available for the full-screen interface):

```sh
bin/snepslog                          # Linux and macOS
bin/sneps
PYTHONPATH=src python3 -m sneps --snepslog      # any system with a POSIX shell
```

The `bin/` launchers work from any directory, so you can also put `bin/` on
your `PATH`.

## How to use it

There are three ways to work with PySNePS: interactively in the terminal
interface, from the command line and in scripts, and as a Python library.
They all run the same SNePS, so you can mix them.

### 1. Interactively, in the terminal interface

This is the best way to learn SNePS.  Start it in a terminal:

```sh
snepslog          # SNePSLOG, the logic interface
sneps             # SNePSUL, the SNePS User Language
```

Then type SNePSLOG statements and questions at the prompt:

```
 PySNePS  SNePSLOG · mode 1 │ context default-defaultct │ trace off          ready
 snepslog❯ man(Socrates).                        │BELIEFS · default-defaultct
   wff1!:  man(Socrates)                         │ ● wff1  man(Socrates)
 snepslog❯ all(x)(man(x) => mortal(x)).          │ ● wff2  all(x)(man(x) => mortal(x))
   wff2!:  all(x)(man(x) => mortal(x))           │ ○ wff3  mortal(Socrates)
 snepslog❯ mortal(?who)?                         │CONTEXTS
   wff3!:  mortal(Socrates)                      │ ▸ default-defaultct  (2 hypotheses)
 snepslog❯ mortal(Zeus)?                         │TERMS
   ↳ no answer: SNePS can't derive that ...      │ man  mortal  Socrates  Zeus
 Tell: man(Socrates).    Ask: mortal(?x)?    Rule: all(x)(man(x) => mortal(x)).
 snepslog❯ _
 F1 Help  F2 Mode  F3 Demos  F4 Trace  ^S Save  ^O Open  ^L Clear  ^Q Quit
```

The keys that matter most:

* **F1** opens the help at the page for the mode you are in.  There are pages
  for getting started, SNePSLOG modes 1, 2 and 3, SNePSUL, Python, SNePS's
  questions and the keys; Left/Right changes the page.  Typing `help mode3`
  (or `snepsul`, `python`, ...) opens a page directly.
* **F2** switches between SNePSLOG modes 1, 2 and 3, SNePSUL, and a Python
  console in which `net` is the knowledge base.  Changing the SNePSLOG mode
  clears the knowledge base, so F2 asks first.
* **F3** runs the demos; **F4** shows the reasoning as SNePS does it.
* When a new belief contradicts the others, SNePS asks you what to do, and
  the choices appear as a menu.
* The side panel shows what SNePS believes (● told, ○ derived), the
  contexts and the terms.
* **Ctrl+S** and **Ctrl+O** save and open knowledge bases, **Ctrl+N** starts
  over, **Ctrl+L** (or `clear`) clears the transcript, **Ctrl+C** interrupts
  a long inference and **Ctrl+Q** quits.

Up/Down recall earlier input and Tab completes commands and terms.

### 2. From the command line and in scripts

With `--classic` (or when the input is not a terminal) the plain SNePS
read-eval-print loop is used, which reads from the keyboard or from a pipe:

```sh
snepslog --classic                                   # the plain SNePSLOG loop
snepslog < my-knowledge.snlog                        # run a file of SNePSLOG input
snepslog --batch --demo "sneps:demo;snepslog;steamroller.snlog"
sneps --batch -e "(define member class)" -e "(assert member Socrates class man)" \
      --save socrates.json                           # save the knowledge base
sneps --restore socrates.json                        # and continue with it later
sneps --batch --demo "sneps:demo;sneps;jobspuzzle.sneps" --export jobs-dataset/
```

`-e INPUT` runs one input as if typed, `--load FILE` loads a SNePSLOG or
SNePSUL file silently (or runs a Python file, for example one that defines
primitive actions), `--fold-case` reads names in lower case so that `Man`
and `man` are the same, `--export DIR` writes a machine-learning dataset on
exit, and `-q` leaves out the banner.  `exit` (SNePSLOG) or `(exit)`
(SNePSUL) leaves the loop.  `python -m sneps [--snepslog]` does the same as
the `sneps` and `snepslog` commands.

### 3. As a Python library

Import `sneps` in your own programs, scripts and notebooks.  Each `Network`
is an independent knowledge base; create as many as you like.

SNePSLOG from Python:

```python
from sneps import Network

net = Network(output=False)          # output=False: silent; by default SNePS prints
net.tell("""
Man(Socrates).
Man(Plato).
all(x)(Man(x) => Mortal(x)).
""")

net.ask("Mortal(Socrates)")          # [M4!]  the derived proposition ([] if unknown)
net.askwh("Mortal(?x)")              # [{'x': Plato}, {'x': Socrates}]
net.askifnot("Mortal(Socrates)")     # []     is the negation derivable?

node = net.ask("Mortal(Plato)")[0]
net.node_text(node)                  # 'Mortal(Plato)'
print(net.snepslog_string([node]))   #   wff6!:  Mortal(Plato)
```

`tell` accepts any SNePSLOG input, several lines at once and commands such
as `set-mode-3`, `define-frame`, `perform` and `clearkb` included, and
returns the result of the last one; `quiet=False` shows the usual output.

SNePSUL from Python:

```python
net = Network(output=False)
net.run_snepsul("""
(define member class subclass superclass)
(assert member Socrates class man)
(assert subclass man superclass animal)
(define-path class (compose class (kstar (compose subclass- superclass))))
""")
net.run_snepsul("(deduce member Socrates class animal)")   # (M3!,)
net.run_snepsul("(find member Socrates)")                  # (M1!, M3!)
```

Acting: primitive actions are Python functions.  Each parameter names an arc
of the act and receives the nodes at that arc.

```python
net = Network(output=False)
net.tell("set-mode-3\ndefine-frame say(action object1)\ndefine-frame Said(nil what)")

@net.python.primaction
def say(object1):
    print([n.name for n in object1])

net.python.attach_primaction("say", say)
for action in ("believe", "snsequence"):
    net.python.attach_primaction(action)               # built-in acts
net.tell("perform snsequence(say(Hello), believe(Said(Hello)))")   # prints ['Hello']
net.ask("Said(Hello)")                                  # [M2!]
```

Saving and loading (as JSON, the format of SNePSUL's `outnet` and `innet`):

```python
from sneps.io import save_network, load_network, serialize
save_network(net, "kb.json")
load_network(Network(), "kb.json")    # replaces the contents of a network
net2 = serialize.load("kb.json")      # or makes a new one
```

### 4. Python inside SNePS

SNePSLOG and SNePSUL escape to Python: `^ code` runs one line of Python and
prints the value of an expression, and `^^` reads Python until a line `^^`.
The code runs in a namespace that belongs to the knowledge base, with `net`,
a `print` that writes to SNePS's output, `node(name)`, `snepsul(text, *args)`,
`tell(text, *args)`, `@primaction` and `attach_primaction`,
`@attached_function` and `attach_function`, and `@command` for new SNePSUL
commands.  This is how the demos define their actions:

```text
: ^^
^^> @primaction
... def say(object1):
...     print("Hello,", object1[0].name)
...
^^> attach_primaction("say", say)
^^> ^^
: perform say(World)
Hello, World
```

In SNePSUL, `(^ expr)` and `^(expr)` can stand for nodes, as in
`(assert member ^(net.node("Socrates")) class man)`.  An entrenchment order
for belief revision can be a Python function too: `set-order f` uses
`f(p, q)` from the namespace.

### 5. For machine learning

`sneps.ml` turns a knowledge base into data.  The exports are deterministic
(nodes in creation order, arcs in SNePS order); numpy, scipy, networkx and
torch are needed only by the functions that use them (`pip install -e
".[ml]"`).  Every function is also a method of `Network`.

```python
net.triples()                    # [('M1', 'a1', 'Socrates'), ('M1', 'r', 'Man'), ...]
net.triples(converse=True)       # ... plus ('Socrates', 'a1-', 'M1'), ...
net.facts()                      # atomic propositions: predicate and arguments
net.fact_triples()               # binary facts as triples: ('Romeo', 'Loves', 'Juliet')
net.propositions()               # one record per proposition, with its supports

g = net.to_networkx(text=True)   # a networkx.MultiDiGraph
t = net.to_tensors(converse=True, relation_counts=True)
t.edge_index, t.edge_type, t.x   # numpy arrays; t.adjacency("a1") is a sparse matrix
t.to_torch()                     # dict of torch tensors (t.to_pyg_dict() for PyG)

from sneps import ml
split = ml.split_triples(net.fact_triples(), ratios=(0.8, 0.1, 0.1), seed=0)
net.export_dataset("out/", kind="facts")   # TSV splits, vocabularies, propositions.jsonl
```

`ml.from_triples(triples)` builds a knowledge base from triples, so data can
also go the other way.

### The demos

The demos of the SNePS 2.8 distribution are included.  Run them with F3 in
the terminal interface, or by their SNePS path:

```text
: demo "sneps:demo;snepslog;socrates.snlog"        all men are mortal
: demo "sneps:demo;snepslog;steamroller.snlog"     Schubert's steamroller
: demo "sneps:demo;snepslog;chap4.snlog"           acting (SNeRE)
: demo "sneps:demo;snebr;autobr.snlog"             automatic belief revision
* (demo "sneps:demo;sneps;jobspuzzle.sneps")       the jobs puzzle in SNePSUL
* (demo)                                           the list of SNePSUL demos
```

## How faithful it is

The translation follows SNePS 2.8 function by function, so programs, demos
and answers are those of the original.  It was checked against it: the demos
of the distribution were run in SNePS 2.8 (under CLISP) and in PySNePS, and
the transcripts compared after normalising case and timing.  The SNePSUL
demos `bidir`, `freeman`, `jobspuzzle`, `uvbr`, the four `numquant` demos and
`dbmsdemo`, and the SNePSLOG demos `agents`, `blackbeard3`, `example1`–`5`,
`freeman`, `jobspuzzle`, `meetings`, `pegasus`, `ruleintro`, `socrates`,
`sourcedMeetings`, `steamroller`, `theorems`, `uvbr` and `yale-shooting` give
the same transcripts, apart from the demos' Lisp code, which is now Python.
The test suite keeps them that way and also covers the other demos.  Where
PySNePS deliberately differs (for example, names keep their case by
default, and Python replaces Lisp), `CHANGES.md` lists the differences.

## For developers

```sh
pip install -e ".[dev]"
pytest                             # unit tests and the demo transcripts
python tests/update_snapshots.py   # update tests/snapshots after an intended change
```

The package: `sneps.core` (nodes, node sets, contexts, build and find,
paths, describe, erase, printing), `sneps.match` (unification), `sneps.snip`
(MULTI, SNIP, rule handlers, SNeRE), `sneps.snebr` (belief revision),
`sneps.snepsul` (reader, evaluator, commands), `sneps.snepslog`,
`sneps.host` (Python as SNePS's host language), `sneps.io` (streams and
saved networks), `sneps.ml` and `sneps.tui` (the terminal interface).

## Credits, rights and license

SNePS was designed and written by **Stuart C. Shapiro and the SNePS Research
Group** at the University at Buffalo, The State University of New York.
**All rights in SNePS are reserved by its original authors** and by the
Research Foundation of State University of New York, on behalf of University
at Buffalo, which holds the copyright of SNePS 2.8.

PySNePS, the translation of SNePS into Python and the additions described
in `CHANGES.md`, is by **numberw8835**.  It was made to help students use
SNePS, and it is free: its changes and additions are covered by the same
license as SNePS, so anyone may use, change and share them.

The Original Code is SNePS 2.8.  The Initial Developer of the Original Code
is the Research Foundation of State University of New York, on behalf of
University at Buffalo.  Portions created by the Initial Developer are
Copyright (C) 2010 Research Foundation of State University of New York, on
behalf of University at Buffalo.  All Rights Reserved.  Contributor:
numberw8835.

SNePS 2.8 is distributed under the University at Buffalo Public License,
version 1.0 (UBPL).  PySNePS is a modification of it and is distributed
under the same license: see `COPYING` for the license text, `CHANGES.md`
for the record of the modifications that the license requires, and the
notice at the top of every source file (for the demos, `NOTICE` in their
directory).

If you use SNePS in your work, cite its authors, for example:

* S. C. Shapiro and W. J. Rapaport, "The SNePS family", *Computers &
  Mathematics with Applications* 23(2–5), 1992, 243–275.
* S. C. Shapiro, "The SNePS semantic network processing system", in
  N. Findler (ed.), *Associative Networks: Representation and Use of
  Knowledge by Computers*, Academic Press, 1979, 179–203.
