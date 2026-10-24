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
"""Texts of the TUI (welcome, help, hints, command descriptions) and the
parser that turns the menus SNePS prints into choices."""

from __future__ import annotations

import re
import textwrap
from typing import NamedTuple

WELCOME = """\
Welcome to PySNePS, the SNePS 2.8 knowledge representation and reasoning system.

You are talking to SNePSLOG, SNePS's logic language. Try these:

    man(Socrates).                      tell SNePS a fact
    all(x)(man(x) => mortal(x)).        tell it a rule
    mortal(?who)?                       ask a question
    list-asserted-wffs                  show what it believes

F1 opens the help for the current mode, F3 the demos; F2 switches to SNePSUL or Python.
"""

WELCOME_SNEPSUL = """\
Welcome to PySNePS, the SNePS 2.8 knowledge representation and reasoning system.

You are talking to SNePSUL, the SNePS User Language. Try these:

    (define member class)                       define two relations
    (assert member Socrates class man)          build and believe a proposition
    (describe *nodes)                           show the network
    (deduce member $who class man)              ask a question

F1 opens the help for the current mode, F3 the demos; F2 switches to SNePSLOG or Python.
"""

HINTS = {
    "snepslog": "Tell: man(Socrates).    Ask: mortal(?x)?    Rule: all(x)(man(x) => mortal(x)).    "
                "Command: list-wffs",
    "sneps": "(define member class)    (assert member Socrates class man)    "
             "(describe *nodes)    (deduce member $x class man)",
    "python": "Python with net = the knowledge base, e.g. net.ask('mortal(Socrates)').  "
              "F2 returns to SNePS.",
    "escape": "Python, e.g. attach_primaction('believe').  Type ^^ to return to SNePS.",
    "pymore": "Python is waiting for the rest of the statement; an empty line ends it.",
    "answer": "SNePS is asking you something: pick an answer in the menu, or type it here.",
    "more": "SNePS is waiting for the rest of your input. Finish it and press Enter.",
    "busy": "SNePS is working…  Ctrl+C interrupts.",
    "exit": "The session has ended. Press Ctrl+Q to leave.",
}

PROMPTS = {"snepslog": "snepslog", "sneps": "sneps", "python": "python", "escape": "python ^^",
           "pymore": "…",
           "answer": "answer", "more": "…"}

HELP_START = """\
GETTING STARTED

SNePS stores what it is told as propositions in a semantic network:
every fact, rule and act is a node.  It reasons with the rules
(backward when you ask, forward when you add a fact with "!"), keeps
track of what each belief depends on, and asks you what to give up
when beliefs contradict each other.

You talk to SNePS in one of these modes.  F2 switches between them,
and F1 shows the help for the mode you are in.  The numbers are the
pages of this help:

  SNePSLOG mode 1  [2]  logic syntax: man(Socrates).  The usual choice.
  SNePSLOG mode 2  [3]  the same syntax; predicates get their own arcs
  SNePSLOG mode 3  [4]  you choose the arcs (define-frame); needed for
                        acting: perform, plans and policies
  SNePSUL          [5]  SNePS's own language, closest to the network:
                        (assert member Socrates class man)
  Python           [6]  a console in which net is the knowledge base;
                        ^ and ^^ run Python from SNePSLOG and SNePSUL

Changing the SNePSLOG mode clears the knowledge base (F2 asks first);
switching between SNePSLOG, SNePSUL and Python keeps it.

A first session in SNePSLOG mode 1:
    man(Socrates).                 tell SNePS a fact
    all(x)(man(x) => mortal(x)).   tell it a rule
    mortal(?who)?                  ask: who is mortal?
    list-asserted-wffs             what SNePS believes now

F3 runs the demos that come with SNePS; they show each mode at work.
When SNePS asks you something, a menu appears: see Questions [7].
The keys and the side panel are explained under Keys [8].
"""

HELP_MODE1 = """\
SNEPSLOG, MODE 1 (the default)

Statements end with a period, questions with a question mark:
    man(Socrates).            a fact (a hypothesis you tell SNePS)
    man(Aristotle)!           a fact, and SNePS reasons forward
    mortal(Socrates)?         is it true?  (SNePS uses the rules)
    mortal(?who)?             which ones?  (?x marks the unknown)
    mortal(Socrates)??        is it believed now, without reasoning?
An answer can be a negation: ~mortal(Zeus) answers mortal(Zeus)?

Rules.  Variables are introduced with all(...); a bare x is a name.
    all(x)(man(x) => mortal(x)).                 if ... then ...
    all(x,y)(parent(x,y) => child(y,x)).         two variables
    all(x)({cat(x), dog(x)} => {pet(x)}).        if any one holds
    all(x)({bird(x), alive(x)} &=> {flies(x)}).  if all of them hold
    all(x)({a(x), b(x), c(x)} 2=> {d(x)}).       if 2 of them hold
    all(x)(round(x) <=> ball(x)).                if and only if
    nexists(_,1,_)(x)(person(x): president(x)).  exactly 1 president

Connectives:
    ~mortal(Zeus).                  not
    man(Plato) and teacher(Plato).  and; also or, <=>
    and{p, q}  or{p, q}  xor{p, q}  nand{p, q}  nor{p, q}  iff{p, q}
    andor(1,1){red(apple), green(apple)}.   1 to 1 of them are true
    thresh(1){p, q}.                        none or all of them

Every proposition has a name like wff3, shown with the answers; a "!"
after it means that SNePS believes it.  wff3? asks it, wff3?? looks
it up, wff3. asserts it, wff3! asserts it and reasons forward.

Commands (Tab completes them and shows what they do):
    list-asserted-wffs     what SNePS believes (list-wffs: all)
    list-terms             the terms (describe-terms: in words)
    clearkb                forget everything (the mode stays)
    trace inference        show the reasoning (F4); untrace inference
    expert                 show what answers depend on; normal
    set-context philo {wff1, wff2}    a context of hypotheses
    set-default-context philo         work in it; list-contexts
    br-mode auto | manual  how contradictions are resolved [7]
    demo "file"   load "file"   exit (leave SNePSLOG)
    %(describe *nodes)     one SNePSUL command [5]
    ^ code   ^^            Python [6]

How mode 1 stores man(Socrates): a node with the arc r to man and a1
to Socrates (a2, a3, ... for more arguments).  Predicates are terms,
so a rule can be about predicates:
    all(r)(symmetric(r) => all(x,y)(r(x,y) => r(y,x))).
    symmetric(friend).
    friend(Ann, Bob).
    friend(Bob, Ann)?
"""

HELP_MODE2 = """\
SNEPSLOG, MODE 2

set-mode-2 switches to mode 2 (it clears the knowledge base).  You
write the same SNePSLOG as in mode 1 [2]: facts, rules, questions and
commands.  Only the network differs: each predicate gets arcs of its
own.

    loves(Romeo, Juliet).

is a node with the arcs " rel loves" to the node loves,
"rel-arg#loves1" to Romeo and "rel-arg#loves2" to Juliet.  Mode 1
uses the arcs r, a1 and a2 for every predicate.

Use mode 2 when the predicates should be relations of their own in
the network: in SNePSUL [5], in path-based inference (define-path)
and in the machine-learning exports (net.triples() in Python [6]).

Try:
    set-mode-2
    loves(Romeo, Juliet).
    all(x,y)(loves(x,y) => cares(x,y)).
    cares(Romeo, ?who)?
    %(describe *nodes)        the network, with the mode 2 arcs

set-mode-1 or set-mode-3 (or F2) changes the mode again.
"""

HELP_MODE3 = """\
SNEPSLOG, MODE 3: CASE FRAMES AND ACTING

set-mode-3 switches to mode 3 (it clears the knowledge base).  In
mode 3 you decide how each predicate is stored, with define-frame:

    define-frame Isa(nil member class) "[member] is a [class]"
    Isa(Socrates, man).       a node with the arcs member and class

The list names the arcs: first the arc for the predicate itself (nil:
the predicate is not stored), then an arc for each argument.  The
optional text describes the proposition for describe-terms
("Socrates is a man.").  Rules, questions, connectives and commands
are as in mode 1 [2]:
    all(x)(Isa(x, man) => Isa(x, mortal)).
    Isa(?who, mortal)?
    describe-terms

Acting (SNeRE).  Mode 3 has frames for the built-in acts believe,
disbelieve, snsequence, snif, sniterate, do-all, do-one, withall,
withsome and achieve, and for the propositions about acting:
ActPlan, GoalPlan, Effect, Precondition, whendo, wheneverdo, ifdo,
if and else.  You write primitive actions in Python [6] and attach
them to their action nodes:

    define-frame say(action object1)
    ^^
    @primaction
    def say(object1):
        print("I say:", object1[0].name)
                                   (an empty line ends the function)
    attach_primaction("say", say)
    attach_primaction("snsequence")   a built-in act, attached too
    ^^
    perform say(Hello)             I say: Hello
    define-frame greet(action object1)
    ActPlan(greet(Stu), snsequence(say(Hi), say(Stu))).
    perform greet(Stu)             SNePS finds the plan and does it
    wheneverdo(Isa(Fido, dog), say(Woof)).
    Isa(Fido, dog)!                the policy fires: I say: Woof

trace acting shows what SNePS decides to do.  In mode 3,
contradictions are resolved automatically (br-mode auto); with
br-mode manual SNePS asks you [7].
"""

HELP_SNEPSUL = """\
SNEPSUL, THE SNePS USER LANGUAGE

SNePSUL works on the network directly.  Define the relations (arc
labels) before you use them:
    (define member class subclass superclass)

Building and believing:
    (assert member Socrates class man)    build a proposition, and
                                          believe it
    (add member Plato class man)          the same, and reason forward
    (assert forall $x ant (build member *x class man)
            cq (build member *x class mortal))      a rule
        $x  a new variable     *x  the value of x
        #x  a new base node    (build ...)  a node inside another
Finding and asking:
    (find member ?who class man)          nodes with these arcs
    (findassert member Socrates)          only the believed ones
    (deduce member $y class mortal)       ask, using the rules
    (deduce 2 member $y class mortal)     at most 2 answers
Looking at the network:
    (describe *nodes)   (describe m1)     m1 also finds node M1
    (full-describe m1)  (dump m1)         supports / raw cables
Paths, for path-based inference (r- is the converse of r):
    (define-path class
      (compose class (kstar (compose subclass- ! superclass))))
        compose, kstar, kplus, converse, or, and; ! = believed nodes
Contexts (named sets of hypotheses):
    (assert member Zeus class god :context olympus)
    (describe-context olympus)   (list-context-names)
    (set-default-context olympus)
And also:
    (find class man) = men     keeps the result in men: *men
    (erase m1)   (resetnet t)   (clear-infer)
    (outnet "kb.json")   (innet "kb.json")    save and load
    (demo)   (demo "sneps:demo;sneps;bidir.sneps")
    (^ len(net.all_nodes()))   ^(expr)   Python [6], also as nodes
    (exit)                     leave SNePSUL
"""

HELP_PYTHON = """\
PYTHON

The Python console (F2, then Python) runs Python with net, the
knowledge base, ready to use:
    net.tell("man(Socrates).")          SNePSLOG input; returns nodes
    net.ask("mortal(Socrates)")         [] if SNePS can't derive it
    net.askwh("mortal(?x)")             [{'x': Socrates}]
    net.run_snepsul("(describe *nodes)")    SNePSUL input
    [n.name for n in net.all_nodes()]
    net.triples()                       the network as triples
    net.to_networkx()  net.to_tensors() for machine learning (these
                                        need numpy and networkx)
A statement that goes on (def, for, if ...) ends with an empty line.

From SNePSLOG and SNePSUL, Python is a keystroke away:
    ^ 6 * 7                one line of Python; prints the value
    ^^                     Python until a line holding ^^
    (^ expr)  ^(expr)      SNePSUL: a Python value as nodes

The code runs in the knowledge base's own namespace, which keeps your
definitions and provides:
    net                    the knowledge base
    print, fresh_line      print into the transcript
    help(net.ask)          Python's documentation of an object
    node("Socrates")       a node by name (None if there is none)
    snepsul("(assert member {} class man)", "Plato")
                           SNePSUL; {} stands for the arguments
    tell("man({}).", "Plato")          the same for SNePSLOG
    @primaction, attach_primaction     acting, see Mode 3 [4]
    @command               a new SNePSUL command, here (isa Plato man):
        @command
        def isa(x, y):
            return snepsul("(assert member {} class {})", x, y)

    @attached_function, attach_function   procedural attachment
A Python function f(p, q) can be the entrenchment order of belief
revision: set-order f (in SNePSLOG) uses it [7].
"""

HELP_QUESTIONS = """\
WHEN SNEPS ASKS YOU SOMETHING

When a new belief contradicts what SNePS believes, SNePS asks you
what to do.  The choices appear as a menu: pick one with the arrow
keys and Enter, or press the key shown in brackets.  Esc closes the
menu, so that you can type the answer at the prompt instead.

A contradiction with something you tell SNePS offers:
    [a]  resolve it: SNePS gives up a hypothesis it trusts least
    [c]  continue, knowing that a contradiction is derivable
    [r]  revise the context yourself: discard some hypotheses
    [d]  discard the new assertion
A contradiction found while reasoning offers [A]ttempt to resolve
it, [C]ontinue, [R]e-start in a consistent context, or [D]rop.

"Which belief should SNePS give up?" lists numbered hypotheses:
choose the one you trust least.  When you revise by hand, SNePS shows
each hypothesis and what depends on it: [d]iscard it, [k]eep it,
[u]ndecided, [q]uit revising, [i]nstructions.  Questions that want
yes or no take y or n.

Try it in SNePSLOG mode 1:
    man(Socrates).
    all(x)(man(x) => mortal(x)).
    mortal(Socrates)?
    ~mortal(Socrates).        contradicts mortal(Socrates): a menu

Settings (SNePSLOG):
    br-mode auto          resolve contradictions without asking
    br-mode manual        ask (the default in modes 1 and 2)
    br-tie-mode auto      don't ask when culprits are equally good
    set-order fluent      give up fluents first; say which
                          predicates are fluents in Python:
                          ^ net.fluents = ["Location"]
    set-order source | explicit | null-order    other orders
    set-order f           a Python function f(p, q) [6]
"""

HELP_KEYS = """\
KEYS
  Enter        send the input      Alt+Enter  new line in the input
  Up/Down      history             Tab        complete a command
  PageUp/Down  scroll              Ctrl+End   jump to the latest output
  F1  help for the current mode    F2  language and mode
  F3  demos    F4  trace reasoning    F5  side panel
  Ctrl+S  save the network         Ctrl+O  open a saved network
  Ctrl+N  start over               Ctrl+L  clear the transcript (or
                                   type clear; what SNePS knows stays)
  Ctrl+C  interrupt a long inference (or clear the input)
  Ctrl+Q  quit (asks first; Ctrl+Q twice quits at once)
  Shift+drag selects text (the TUI uses the mouse for scrolling and
  for the menus).

IN THE HELP
  Left/Right or Tab change the page, 1-8 open a page, Up/Down and
  PageUp/Down scroll, Esc or F1 closes.  "help mode3" at the prompt
  opens a page directly: start, mode1, mode2, mode3, snepsul, python,
  questions, keys.

THE SIDE PANEL
  Beliefs are the propositions SNePS believes in the current context.
  A filled dot means you told it (a hypothesis); a hollow dot means
  SNePS derived it.  Contexts are named belief spaces (set-context,
  set-default-context); the current one is marked.  Terms are the
  individuals and predicates SNePS knows about.  F5 hides the panel.

THE TOP LINE
  The language and mode, the current context, whether reasoning is
  traced, and whether SNePS is working, ready or asking you something.
"""

#: The help pages: (key, tab label, text).
HELP_TOPICS = [
    ("start", "Start", HELP_START),
    ("mode1", "Mode 1", HELP_MODE1),
    ("mode2", "Mode 2", HELP_MODE2),
    ("mode3", "Mode 3", HELP_MODE3),
    ("snepsul", "SNePSUL", HELP_SNEPSUL),
    ("python", "Python", HELP_PYTHON),
    ("questions", "Questions", HELP_QUESTIONS),
    ("keys", "Keys", HELP_KEYS),
]

#: Other words that "help WORD" accepts for a page.
HELP_ALIASES = {"intro": "start", "snepslog": "mode1", "snepslog1": "mode1",
                "snepslog2": "mode2", "snepslog3": "mode3", "frames": "mode3",
                "acting": "mode3", "sneps": "snepsul", "py": "python",
                "contradictions": "questions", "revision": "questions", "panel": "keys"}


def fit_text(text: str, width: int) -> str:
    """TEXT with the lines longer than WIDTH wrapped at spaces; the parts
    after the first are indented a little more than the line itself."""
    out: list[str] = []
    for line in text.splitlines():
        if len(line) <= width:
            out.append(line)
            continue
        indent = " " * min(len(line) - len(line.lstrip()) + 4, width // 2)
        out.extend(textwrap.wrap(line, width, subsequent_indent=indent,
                                 break_on_hyphens=False) or [""])
    return "\n".join(out)


def help_topic(kind: str, dialect: str, snepslog_mode: int) -> str:
    """The help page for the state of the session."""
    if kind in ("python", "escape", "pymore"):
        return "python"
    if kind == "answer":
        return "questions"
    if kind == "sneps" or (kind not in ("snepslog",) and dialect == "sneps"):
        return "snepsul"
    return f"mode{snepslog_mode}" if snepslog_mode in (1, 2, 3) else "mode1"


SNEPSLOG_COMMANDS = {
    "activate": "reason forward from a proposition",
    "activate!": "assert and reason forward",
    "add-to-context": "add hypotheses to a context",
    "ask": "ask whether a proposition holds",
    "askifnot": "ask whether a proposition is false",
    "askwh": "ask a wh-question (returns bindings)",
    "askwhnot": "ask which instances are false",
    "beliefs-about": "propositions about a term",
    "br-mode": "belief revision: auto or manual",
    "br-tie-mode": "belief revision ties: auto or manual",
    "clear-infer": "forget the results of earlier inference",
    "clearkb": "start over with an empty knowledge base",
    "copyright": "copyright information",
    "define-frame": "define a case frame (mode 3)",
    "define-path": "define a path-based inference rule",
    "demo": "run a demo file",
    "describe-context": "show a context",
    "describe-terms": "show terms in detail",
    "expert": "show supports with every answer",
    "exit": "leave SNePSLOG",
    "list-asserted-wffs": "what SNePS believes now",
    "list-contexts": "all named contexts",
    "list-terms": "all terms",
    "list-wffs": "all propositions",
    "load": "load a SNePSLOG file",
    "normal": "normal output (undo expert/unlabeled)",
    "perform": "carry out an act",
    "remove-from-context": "remove hypotheses from a context",
    "set-context": "define a named context",
    "set-default-context": "switch to a context",
    "set-mode-1": "mode 1: predicates as terms (clears the KB)",
    "set-mode-2": "mode 2: predicates as relations (clears the KB)",
    "set-mode-3": "mode 3: case frames (clears the KB)",
    "set-order": "belief revision ordering",
    "show": "show the network",
    "trace": "trace inference, acting, translation or parsing",
    "undefine-path": "remove a path definition",
    "unlabeled": "answers without wff labels",
    "untrace": "stop tracing",
}


class Option(NamedTuple):
    answer: str       # what is sent to SNePS
    label: str        # what the menu shows
    key: str = ""     # shortcut key


_BRACKET = re.compile(r"\[(\w)\]")
_NUMBERED_ITEM = re.compile(r"^\s*(\d+)\s*:\s*(.*\S)")
_PLEASE_TYPE = re.compile(r"\(please type ([^)]*)\)|Enter '(y)' or '(n)'", re.IGNORECASE)


def _letter_options(line: str) -> list[tuple[str, str]]:
    """The "[x] label" options on one line of a menu."""
    found = list(_BRACKET.finditer(line))
    out = []
    for k, m in enumerate(found):
        end = found[k + 1].start() if k + 1 < len(found) else len(line)
        rest = line[m.end():end]
        glued = bool(rest) and not rest[0].isspace()      # "[a]ttempt" vs "[a] to attempt"
        rest = rest.strip().rstrip(";,.").strip()
        if glued:
            label = m.group(1) + rest
        else:
            label = rest[3:] if rest.startswith("to ") else rest
        label = label or m.group(1)
        out.append((m.group(1).lower(), label[0].upper() + label[1:]))
    return out


def parse_menu(lines: list[str]) -> list[Option]:
    """The answers a SNePS question offers, from the lines printed before it.

    Recognizes the belief-revision menus ("[a] ...", "1. [A]ttempt ...",
    numbered hypothesis lists) and y/n questions; returns [] for free-form
    questions such as "Enter a hypothesis ..."."""
    text = "\n".join(lines)
    start = text.rfind("=><=")
    block = text[start + 4:] if start >= 0 else text
    asks = list(_PLEASE_TYPE.finditer(block))
    wants = ""
    if asks:
        m = asks[-1]
        wants = (m.group(1) or "y or n").lower()
    numbered = ("number" in wants or "least like to keep" in block
                or "list number" in block)
    options: list[Option] = []
    if numbered:
        for line in block.splitlines():
            m = _NUMBERED_ITEM.match(line)
            if m:
                options.append(Option(m.group(1), m.group(2)[:100], m.group(1)))
    if wants:
        allowed = set(re.findall(r"\b([a-z])\b", wants))
        seen = set()
        for line in block.splitlines():
            for letter, label in _letter_options(line):
                if letter in allowed and letter not in seen:
                    seen.add(letter)
                    options.append(Option(letter, label, letter))
        if not seen and allowed == {"y", "n"}:
            options += [Option("y", "Yes", "y"), Option("n", "No", "n")]
    return options
