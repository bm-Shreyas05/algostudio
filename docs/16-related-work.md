# 16 — Comparison with Existing Systems

*(Deliverable AB; §36 of the brief)*

The brief is explicit: **do not falsely claim that these systems lack features.** Several of
them do things AlgoStudio does not, and some do them better. This document is written so
that a reviewer who knows these tools well finds it accurate.

---

## AB.1 What each system actually is

### Python Tutor (Guo, 2013)
The closest prior art and the most important comparison. Executes real Python (also C, C++,
Java, JS) with `sys.settrace`, producing a full per-step trace of frames and heap objects,
rendered as boxes and arrows with forward *and backward* stepping.

**Does well:** correct execution of a wide Python subset; the frames/heap/arrows model of
aliasing is excellent and is the model we adopt; already has step-back; runs at enormous
scale in the classroom; multi-language.

**Does not attempt:** sub-statement events (no condition values, no distinct subscript
reads, no expression operands); data-structure-appropriate views (a graph adjacency dict
renders as a dict of lists, always); execution analytics; semantic/algorithm-level events;
an extension model for new views or algorithms; AI explanation.

*Correction to a common misstatement:* Python Tutor **does** support stepping backwards. Any
claim that time travel is our novelty is false. What we add is *why* the value changed —
provenance through the causal chain — not merely *what* it was.

### VisuAlgo (Halim et al.)
A large, polished library of hand-authored algorithm visualizations with excellent
pedagogical framing, quizzes, and multilingual support.

**Does well:** visual quality; pedagogical sequencing; breadth (~30 topics); e-lecture mode;
auto-generated assessment. For *learning a named algorithm*, it is better than what we build.

**Does not attempt:** running the user's own code. Visualizations are authored per
algorithm. There is no execution engine; the animation is the artifact.

### Algorithm-Visualizer (algorithm-visualizer.org)
Open source. Users write JS/Java/C++ and call a **tracer API** (`tracer.select(i)`,
`tracer.patch(...)`) to emit visualization commands, which are rendered by generic
components.

**This is the closest system to our semantic-event idea and must be acknowledged as such.**
Its `tracer` API is essentially our `algo.*` API. The architectural differences are:

| | Algorithm-Visualizer | AlgoStudio |
|---|---|---|
| Source of visualization | **explicit tracer calls only** | tracer calls **or** automatic instrumentation **or** lifted from generic events |
| Un-annotated code | produces nothing | produces full generic visualization |
| Generic program state (frames, heap, aliasing) | not modelled | first-class |
| Time travel | replay of the command log (forward/back) | reducer + inverse reducer over a typed state model |
| Analytics | no | derived from events |
| Grounded AI | no | yes |

The honest summary: they solved the "semantic events" half; we argue the interesting problem
is getting those semantics **without requiring annotation**, and combining them with a real
program-state model.

### USFCA / David Galles' visualizations
Small, fast, dependency-free JS animations, one per data structure/algorithm. Long-standing
and widely used.

**Does well:** clarity, speed, zero setup, precise control over the animation.
**Does not attempt:** anything to do with user code, execution, or generality.

### VS Code Debugger (DAP), `pdb`, PyCharm
Production debuggers over the Debug Adapter Protocol.

**Does well:** correctness, real breakpoints (including conditional and data breakpoints),
watch expressions, live variable modification, attach-to-process, multi-threading, remote
debugging. All of these are things AlgoStudio does *not* do, and several are things it
architecturally *cannot* do in its MVP form because it replays a recording rather than
controlling a live process. This should be stated plainly in the report.

**Does not attempt:** visual data-structure representation beyond a variable tree; execution
history (`pdb` is forward-only; `rr`-style reverse execution is not in the standard Python
tooling); analytics; pedagogical framing.

### Jupyter
Not a debugger. Cell-level execution with rich display of *results*.

**Does well:** exploration, incremental execution, plotting, narrative — a genuinely
different and complementary model.
**Does not attempt:** step-level execution visualization. (`ipdb` exists but is a text
debugger inside a cell.)

### `rr`, Chronon, TOD, Elm's time-travelling debugger
Genuine omniscient/back-in-time debuggers.

**Do well:** the record-and-reverse-execute problem, at production quality and (for `rr`) at
native-code scale with hardware-assisted determinism. **Our time-travel design is not novel
relative to this literature** and we cite it as prior art.
**Do not attempt:** education, data-structure visualization, semantic abstraction of program
operations.

### Others worth naming in the report
Jeliot 3 (automatic Java animation from execution — the closest historical relative of the
"derive, don't author" idea, and it should be cited prominently), JHAVÉ, ANIMAL, Online
Python Tutor's C/C++ backend (Valgrind-based), Thonny (an excellent teaching IDE with
step-into-expression evaluation — notably, Thonny *does* visualize sub-expression
evaluation, which is closer to our granularity than Python Tutor is), SeeC, Codeboard.

**Thonny deserves special mention:** its stepper shows expression evaluation step by step,
which overlaps directly with our `EXPRESSION_EVALUATED`/`CONDITION_EVALUATED` events. Its
scope is a desktop IDE for beginners rather than a platform, and it has no data-structure
views, analytics, or extensibility model — but the claim "nobody shows sub-expression
evaluation" would be false.

---

## AB.2 Honest feature matrix

Legend: ● full · ◐ partial · ○ none · — not applicable

| Capability | Python Tutor | VisuAlgo | Algo-Visualizer | USFCA | VS Code | Thonny | `rr` | **AlgoStudio (MVP)** |
|---|---|---|---|---|---|---|---|---|
| Runs user's own code | ● | ○ | ● | ○ | ● | ● | ● | ● |
| Multiple languages | ● | — | ● | — | ● | ○ | ◐ | ○ *(design only)* |
| Real execution (not simulated) | ● | ○ | ● | ○ | ● | ● | ● | ● |
| Step forward | ● | ● | ● | ● | ● | ● | ● | ● |
| **Step backward** | ● | ● | ● | ● | ○ | ○ | ● | ● |
| Sub-expression / condition values | ○ | — | ○ | — | ◐ | ● | ◐ | ● |
| Frames + heap + aliasing model | ● | ○ | ○ | ○ | ◐ | ◐ | ◐ | ● |
| Data-structure-specific views (array/graph/tree) | ○ | ● | ● | ● | ○ | ○ | ○ | ● |
| **Views chosen automatically from runtime structure** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| Algorithm-level semantics (swap/compare/relax) | ○ | ● *(authored)* | ● *(annotated)* | ● *(authored)* | ○ | ○ | ○ | ● *(annotated **and** inferred)* |
| **Semantics inferred from un-annotated code** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| Execution analytics / op counting | ○ | ◐ | ○ | ◐ | ○ | ○ | ○ | ● |
| Algorithm comparison on identical input | ○ | ◐ | ○ | ○ | ○ | ○ | ○ | ◐ *(V2 for synced replay)* |
| Real breakpoints on a live process | ○ | — | ○ | — | ● | ● | ● | ○ *(replay-side only)* |
| Conditional / data breakpoints | ○ | — | ○ | — | ● | ◐ | ● | ○ *(V2)* |
| Modify state and continue | ○ | — | ○ | — | ● | ○ | ◐ | ○ |
| Threads / async | ○ | — | ○ | — | ● | ◐ | ● | ○ |
| Native code / system calls | ◐ | — | ○ | — | ● | ○ | ● | ○ |
| Plugin architecture for new algorithms | ○ | ○ | ◐ | ○ | — | — | — | ● |
| AI explanation | ○ | ○ | ○ | ○ | ◐ *(Copilot, source-grounded)* | ○ | ○ | ● *(state-grounded)* |
| **Verified AI claims against execution** | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ● |
| Production maturity / scale | ● | ● | ◐ | ● | ● | ● | ● | ○ |

The bottom row matters. These are mature, widely used systems. AlgoStudio is a
research prototype and the report should say so.

---

## AB.3 Where our architecture differs — the three rows that matter

Everything else in the matrix is a feature; these three are *architectural*.

**1. Views chosen automatically from runtime structure.**
Every other system either authors the view per algorithm (VisuAlgo, USFCA), requires the
programmer to specify it (Algorithm-Visualizer), or shows one uniform view (Python Tutor).
Choosing the view by *classifying the heap object's structure* is the mechanism that makes
"a student's unseen algorithm gets an appropriate visualization" possible.

**2. Semantics inferred from un-annotated code.**
Algorithm-Visualizer proves annotation works. Our claim is narrower and more interesting:
`arr[i], arr[j] = arr[j], arr[i]` written by a student who has never heard of our API still
produces a `SWAP` event, because the lifter matches the *idiom* in the generic event stream.
This is what allows semantic visualization of code we do not control.

**3. AI claims verified against the execution record.**
Grounding an LLM in retrieved context is standard. Grounding it in a *recorded execution*
and then **mechanically checking its factual claims against that recording** is not, and it
is only possible because the execution is a queryable typed record rather than a rendering.

---

## AB.4 What we are giving up, explicitly

| We lack | Which system has it | Why we accept the loss |
|---|---|---|
| Real live breakpoints, modify-and-continue | VS Code, `pdb` | Requires a control channel into the sandbox; the replay model covers the teaching need and is safer |
| Threads, async, native code | VS Code, `rr` | Out of the educational subset; would multiply the event model's complexity |
| Multi-language today | Python Tutor | One language done properly is the evidence; the interface exists for the rest |
| Visual polish and curated pedagogy | VisuAlgo | They hand-tuned each animation over years; derived views will look plainer. This is the central trade the project makes, and RQ1 measures how much it costs |
| Production scale and reliability | all of them | Prototype |

---

## AB.5 One-paragraph positioning (for the abstract)

> Existing educational tools sit at two poles. Curated visualizers such as VisuAlgo and the
> USFCA animations offer excellent, hand-authored presentations of named algorithms but
> cannot run a student's own code. Generic execution visualizers such as Python Tutor run
> real code and, like AlgoStudio, support stepping backwards, but present every program
> through a single uniform frames-and-heap view with no sub-statement detail and no
> algorithm-level abstraction. Systems such as Algorithm-Visualizer bridge the two by having
> the programmer emit explicit visualization commands. AlgoStudio's contribution is to make
> both the visualization *and* the algorithm-level semantics **derivable from a recorded
> execution**: structural detectors choose data-structure-appropriate views from the runtime
> heap, and idiom lifters recover operations such as *swap*, *compare* and *relax* from
> un-annotated code. The same recording then grounds an AI tutor whose factual claims are
> automatically verified against it. We evaluate how far this derivation extends across
> twenty algorithms, and report the classes where it does not.
