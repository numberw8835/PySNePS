# Changes

PySNePS is a Modification of SNePS 2.8. It is derived directly from the
Original Code provided by the Initial Developer, the Research Foundation of
State University of New York, on behalf of University at Buffalo, and is
distributed under the University at Buffalo Public License 1.0 (see `COPYING`).
Every source file carries the license's Exhibit A notice.

This file records the changes made to the Original Code, as section 3.3 of the
license requires.

## 2026-10-22: translation to Python

The SNePS 2.8 Common Lisp sources were translated to Python, function by
function:

| SNePS 2.8 (Lisp)                      | PySNePS (Python)                     |
|---------------------------------------|--------------------------------------|
| `sneps/ds`, `sneps/fns`               | `sneps.core`, `sneps.snepsul`        |
| `match`                               | `sneps.match`                        |
| `multi`                               | `sneps.snip.multi`                   |
| `snip` (inference, rules, SNeRE)      | `sneps.snip`                         |
| `snebr`                               | `sneps.snebr`                        |
| `snepslog`                            | `sneps.snepslog`                     |
| `sneps/fns/outnet.lisp`, `innet.lisp` | `sneps.io.lispnet` (removed later)   |
| demo files (`demo/`)                  | `sneps/data/demo/` (copied unchanged)|

New in PySNePS (not part of the Original Code):

- `sneps.lisp`: a Lisp reader, printer, `FORMAT` and an interpreter for the
  Common Lisp subset that SNePSUL programs and the demos embed (`^`, `^^`,
  `#!`, `defsnepscom`, `define-primaction`, ...). In the original, the host Lisp
  provided these. (Removed on 2026-10-24, see below.)
- Library structure: no global state. Each `sneps.Network` is an independent
  network with its own top levels, variables and inference queues.
- `sneps.io.serialize`: saving and restoring networks as JSON. `outnet` and
  `innet` use JSON when the file name ends in `.json`.
- `sneps.ml`: exports for machine learning (networkx graphs, triples and
  vocabularies, tensors and sparse adjacency, datasets).
- A command-line interface (`sneps`, `snepslog`, `python -m sneps`) and a
  pytest suite.

## 2026-10-22: terminal interface

- `sneps.tui`: a full-screen interface on top of the unchanged SNePSLOG and
  SNePSUL loops. It provides input editing, completion and history,
  colour-coded output, a side panel with beliefs, contexts and terms, menus for
  SNePS's questions, language and mode switching, demos, save/open, tracing
  and interruption. It is the default in a terminal; `--classic` gives the
  original loops.
- `Network.interrupt()` stops a running inference: the MULTI scheduler checks
  the request between processes and reports a SNePS error.
- SNePS's top levels pin the Lisp reading mode (SNePSUL semantics) on entry,
  so they behave the same when started from a Lisp loop.

## 2026-10-24: no Lisp

PySNePS no longer contains or emulates Lisp; Python is SNePS's host language.

- Removed `sneps.lisp` (the Lisp reader, printer, `FORMAT` and interpreter),
  the Lisp function table of SNePSUL (`sneps/snepsul/lispfns.py`), the SNePS
  2.7 network file format (`sneps.io.lispnet`) and the Common Lisp sequence
  helpers (`sneps/util/cl.py`, replaced by `sneps/util/lists.py`, which keeps
  the element orders SNePS depends on).
- `sneps.snepsul.reader`: a reader for SNePSUL's own syntax that produces
  plain Python data (names are `str`, string literals
  `sneps.core.printing.Text`); `sneps.core.printing` writes SNePS data and
  node descriptions. Both replace the Lisp reader and printer.
- The SNePSUL evaluator dispatches commands itself. Commands return a
  `Result` (value and context) instead of Lisp multiple values. SNePSLOG
  translates its own commands into Python callables instead of Lisp forms,
  and code inside SNePS that built Lisp forms (procedural attachment, the
  `adopt` and `unadopt` actions, belief revision, `find_nodes`) calls Python
  directly, as top-level commands as before, so belief revision re-runs the
  same thing.
- `sneps.host`: the `^` and `^^` escapes of SNePSLOG and SNePSUL run Python
  in a namespace that belongs to the network (`net`, `print`, `node`,
  `snepsul`, `tell`, `@primaction`, `attach_primaction`,
  `@attached_function`, `attach_function`, `@command`, `undefine_commands`).
  `set-order` accepts a Python function from that namespace. The demo pause
  key `^` enters Python.
- The SNePSLOG command `lisp` and the SNePSUL command `(lisp)` are replaced
  by `exit` and `(exit)`. `lispeval` is gone. In the terminal interface, the
  Lisp mode is replaced by a Python console where `net` is the network.
- `outnet`, `innet`, `save_network` and `load_network` use JSON only.
  `--load` runs Python files (`.py`) instead of Lisp files.
- `tell(text, *args)` fills `{}` fields (Python `str.format`) instead of Lisp
  `FORMAT` directives.
- SNePSUL forms in messages are written with SNePSUL's abbreviations
  (`(build forall ($x) arg *x)`) instead of Lisp quotes (`(($ 'x))`).
- Demos: the Lisp parts of `dbms/dbmsdemo.sneps`, `snepslog/agents.snlog`,
  `snepslog/chap4.snlog`, `snepslog/duck.snlog`, `snebr/autobr.snlog`,
  `sneps/clue.sneps` and `sneps/sneps79.sneps` (renamed from `sneps79.lisp`)
  were rewritten in Python; their inferences and other output are unchanged.
  The Emacs Lisp mode lines were removed from the demo files. Removed: the
  `activation` demo (it needs the XGinseng Lisp interface), `brachet` (a
  contextual vocabulary acquisition program written in Lisp, which is
  natural-language processing) and `demo-info.lisp` (the menu is in
  `sneps/snepslog/demos.py`).
- Comments and docstrings name the original SNePS 2.8 modules without the
  `.lisp` suffix.

## 2026-10-24: clearing the terminal interface

- Ctrl+L, or typing `clear` (or `cls`), empties the transcript of the
  terminal interface. The knowledge base, the side panel and the input
  history are kept. The footer and the F1 help list the key.

## 2026-10-24: help for each mode

- The help of the terminal interface (F1, or typing `help`) has a page for
  each mode: getting started, SNePSLOG modes 1, 2 and 3, SNePSUL, Python,
  SNePS's questions (belief revision), and the keys and side panel. It opens
  at the page of the current mode; Left/Right, Tab or the number keys change
  the page, and `help <page>` opens one. Pages are word-wrapped to the width
  of the terminal.
- In the Python namespace, `help(object)` writes Python's documentation into
  SNePS's output.

## Differences in behaviour

- **Case.** Names keep their case, as in Allegro CL's "modern" mode.
  Built-in relation and command names are lower case, and generated node names
  are upper case (`M1`, `V2`). Typing `m1` finds node `M1`. With
  `Network.fold_case = "lower"` (`--fold-case`), names are read in lower case,
  so they are case-insensitive as in SNePS under a Lisp that upcases symbols.
- **Python instead of Lisp.** SNePS's escapes to its host language (`^`,
  `^^`, primitive actions, attached functions, user-defined commands) use
  Python. The chap4 demo turns plan tracing on where it intends to; in the
  original, its `(setf *plantrace* 'surface)` set a variable of the wrong
  package and had no effect.
- **Errors.** A SNePS error prints its message and returns to the top level;
  there is no "Do you want to debug it?" prompt or Lisp debugger. Unexpected
  Python errors inside a top level are reported the same way, and errors in
  Python escapes print a Python traceback.
- **Demo pauses.** Pause points read one line from the terminal (RETURN,
  `c`, `q`, `a`, `^`, `s`, `o`, `p`, `?`; `^` enters Python where the original
  entered Lisp). The `dc-*` demo control commands work as in the original.
- **Network files.** `outnet` and `innet` write and read PySNePS' JSON
  format, not the SNePS 2.7 network file format. The JSON records nogoods.
- Printing does not reproduce CLISP's pretty-printer habits: CLISP starts
  strings that contain newlines on a fresh line, and wraps lines around
  `|...|` escapes.

## Not ported

- The SNePS natural-language tools (SNaLPS: `nlint/`, the English morphology
  and lexicon, the GATN parser and generator). The demos that need them,
  `demo/nlint` and `demo/snere` (which also needs the Garnet graphics and
  ARC/INFO), are not included.
- The XGinseng and Garnet graphical interfaces, `SnepsGUI`, `JavaSnepsAPI` and
  `Jlinker`, and the `activation` demo, which needs XGinseng.
- The Lisp interface of SNePS: running Lisp code inside SNePS, the Lisp
  functions SNePS exports to Lisp programs, `#!` and `defsnepscom`. Python
  takes their place (see 2026-10-24).
- The `brachet` contextual vocabulary acquisition demo (a Lisp program).
- The `defaults` demos rely on a separate implementation of default rules that
  is not part of SNePS 2.8, so they stop at the first default rule, as in the
  original.

## Verification

The bundled SNePSUL and SNePSLOG demos were run in SNePS 2.8 under CLISP and
in PySNePS, and the transcripts were compared. These give identical output:
bidir, dbmsdemo, freeman, jobspuzzle, numquant (jobspuzzle, meeting, mother,
owner), uvbr, snepslog/pegasus.sneps, and the SNePSLOG demos agents,
blackbeard3, example1-5, freeman, jobspuzzle, meetings, pegasus, ruleintro,
socrates, sourcedMeetings, steamroller, theorems, uvbr and
defaults/yale-shooting.snlog. duck is identical apart from CLISP's line
wrapping. The remaining demos differ only in the ways listed above, or at
the point where CLISP itself stops reading input.

After the Lisp layer was removed (2026-10-24), every demo was run with the
code before and after the change and the transcripts compared: they are
identical apart from the demos' Lisp code, now Python, and the printing of
SNePSUL forms in parse warnings. The test suite keeps snapshots of all
bundled demos.
