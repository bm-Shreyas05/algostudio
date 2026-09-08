# 00 — Project Definition, Problem Statement, Motivation, Objectives

*(Deliverables A–E)*

---

## A. Refined Project Definition

AlgoStudio is a **general-purpose program execution visualization platform** built around a
language-agnostic, event-sourced execution model.

The system does not visualize *algorithms*. It visualizes *executions*. An execution is
reduced to a totally-ordered, strongly-typed stream of semantic events; every downstream
capability — time-travel debugging, variable inspection, data-structure rendering,
complexity analytics, AI explanation — is a **pure function of that event stream**.

Formally, the system implements the pipeline:

```
S   : SourceText                                  (user program, language L)
F_L : SourceText -> IR                            (language frontend: parse, validate, lower)
I   : IR -> InstrumentedProgram                   (instrumentation / execution plan)
X   : InstrumentedProgram x Input -> [Event]      (sandboxed execution)
R   : ExecutionState x Event -> ExecutionState    (reducer, total)
R'  : ExecutionState x Event -> ExecutionState    (inverse reducer, partial)
V   : ExecutionState -> [ViewDescriptor]          (view resolution)
A   : [Event] -> Analytics                        (fold)
G   : [Event] x ExecutionState x Question -> Answer   (grounded explanation)
```

The engineering contribution is the design of the `Event` algebra and the pair `(R, R')`
such that:

1. `R` is **total** — every event is applicable to any reachable state.
2. `R'` is **exact** on all mutating events — enabling O(1) reverse stepping.
3. `V` depends only on **structural properties** of state, never on algorithm identity.
4. `F_L` is the **only** language-specific component.

Three architectural invariants follow, and they are the acceptance criteria for the whole
project:

| Invariant | Statement | How it is enforced |
|---|---|---|
| **INV-1** | Adding an algorithm changes **zero** core files. | Algorithms are metadata + ordinary source, discovered by a registry scan. Enforced by `tests/test_plugin_isolation.py`. |
| **INV-2** | Adding a language changes **zero** files in `state/`, `lifters/`, `shapes/`, `analytics/`, `ai/`, `api/`, or the frontend. | Frontends implement `LanguageFrontend` and emit the shared `Event` schema. |
| **INV-3** | Any step *n* of any execution is reconstructible without re-running the program. | Event sourcing + checkpoints; `R'` for reverse steps. |

### What it explicitly is not

- Not a library of hand-authored animations keyed on algorithm name.
- Not a CRUD app with a chatbot bolted on. The LLM consumes the engine's output; it is
  never in the execution path and never a source of execution facts.
- Not a claim to visualize arbitrary Python. See `19-capability-matrix.md` for the exact,
  tested support boundary and the graceful-degradation behaviour outside it.

---

## B. Final Project Title

> **AlgoStudio: A Language-Agnostic, Event-Sourced Execution Model for General-Purpose
> Program Visualization, Time-Travel Debugging, and State-Grounded AI Explanation**

Short form: **AlgoStudio — Universal Event-Driven Program Execution and Visualization Platform**

---

## C. Problem Statement

Program execution is invisible. Students learning data structures and algorithms must
maintain a mental simulation of a machine they cannot observe: bindings, aliasing, the
call stack, and the evolving shape of heap data. Existing educational tooling addresses
this in three incompatible ways, each with a structural limitation:

1. **Curated algorithm visualizers** (VisuAlgo, USFCA/Galles, Algorithm Visualizer) render
   pedagogically-tuned animations — but each animation is *hand-written per algorithm*.
   The visualization is authored, not derived. A student's own code cannot be visualized
   at all, and the marginal cost of a new algorithm is a new animation module.

2. **Generic execution visualizers** (Python Tutor) do derive their display from real
   execution and accept largely arbitrary code — but the derived display is deliberately
   *uniform*: frames, objects, arrows. Execution is presented at a single granularity,
   there is no semantic layer above "a variable changed", no per-execution analytics, and
   no notion of algorithm-level operations such as *compare* or *relax*.

3. **Professional debuggers** (the VS Code / DAP debugger, `pdb`) provide exact state at a
   breakpoint but present it as text trees, run forward only by default, and are designed
   for engineers who already know what they are looking for.

Neither family provides the property that matters educationally: **a single execution
record that is simultaneously (a) derived from the student's own code, (b) navigable
backwards in time, (c) rich enough that domain-appropriate visualizations can be selected
automatically, and (d) precise enough that an AI tutor can be constrained to it.**

The problem this project addresses is therefore:

> **Design and implement an execution model, expressive enough that both generic program
> state and algorithm-level semantics can be recovered from a single event stream, and
> structured enough that visualization, analytics, and explanation can be derived
> mechanically — without per-algorithm or per-language code in the presentation layer.**

---

## D. Motivation

**D1. The marginal-cost argument.** In a curated visualizer, cost(new algorithm) is
approximately cost(new animation). In AlgoStudio, cost(new algorithm) is approximately
cost(writing the algorithm), because the visualization is a function of the events the
algorithm's execution already produces. This is measurable, and we measure it (§AA:
*core files changed per added algorithm*, target = 0).

**D2. The student's own code is the artifact that matters.** A student debugging *their*
broken merge sort gains nothing from a perfect animation of a *correct* merge sort. The
gap between "here is how it should work" and "here is what your code did" is exactly where
learning happens, and it is the gap curated visualizers cannot cross.

**D3. Backwards is where understanding lives.** The question a confused student asks is
almost never "what happens next?" — it is "*wait, how did `high` become 3?*". Answering
that requires reverse navigation to the write that produced the value, which requires an
execution record, which requires event sourcing. Forward-only tools structurally cannot
answer the question that is actually asked.

**D4. LLMs hallucinate execution.** Ask a language model "why did `mid` become 4 here?"
with only source code in context and it will produce a plausible trace. It is answering
from the *distribution of programs like this one*, not from *this run*. If the model
instead receives the actual bindings, the actual condition results, and the actual
preceding events, the explanation is constrained by fact. This is a testable hypothesis
(§Z, RQ3) and the engine is what makes the test possible.

**D5. Generality is an architectural claim worth testing.** "Visualization can be derived
rather than authored" is a design hypothesis. It might be false — some algorithms may
genuinely need authored views. Building the system is how we find out, and honest
reporting of where derivation fails is a legitimate result.

---

## E. Objectives

### Primary (MVP — must be demonstrated)

| # | Objective | Acceptance criterion |
|---|---|---|
| O1 | Define an extensible, strongly-typed event model for program execution. | JSON Schema published; 40+ event types; round-trip serialization test passes. |
| O2 | Implement a Python frontend producing that event stream. | AST-instrumentation frontend; capability matrix tested feature-by-feature. |
| O3 | Execute untrusted code under a documented isolation policy. | No filesystem/network/`import os` escape in the sandbox test suite; infinite loops terminate deterministically. |
| O4 | Reconstruct exact state at any step without re-execution. | `state(n)` from checkpoint+replay is identical to `state(n)` from full forward replay, for every n, on every fixture program. |
| O5 | Support O(1) reverse single-step. | `R'(R(s,e),e) == s` property test over generated event sequences. |
| O6 | Derive visualizations from state structure, not algorithm identity. | Zero occurrences of algorithm names in `frontend/src/views/**` — enforced by a lint test. |
| O7 | Support algorithm plugins with zero core modification. | Adding `bubble_sort` touches only `algorithms/bubble_sort/**` — enforced by a path-manifest test. |
| O8 | Provide state-grounded AI explanation. | Explanation endpoint receives only serialized state; a verifier checks every numeric claim against state. |
| O9 | Collect execution analytics automatically. | Comparisons / swaps / array-accesses / recursion-depth derived from generic events, not from algorithm-specific counters. |
| O10 | Ship 4 reference algorithms + 1 user-authored algorithm demo. | Binary Search, Merge Sort, BFS, Dijkstra + live-typed custom algorithm in the demo. |

### Secondary (V2)

O11 graph/tree input editors · O12 side-by-side algorithm comparison · O13 replay-side
breakpoints with step over/into/out · O14 session persistence and sharing · O15 static
pre-execution analysis surfaced in the UI.

### Research (evaluated, not merely built)

| # | Objective |
|---|---|
| O16 | Quantify instrumentation overhead as a function of event granularity. |
| O17 | Measure engineering effort to add an algorithm (files touched, LOC, wall-clock). |
| O18 | Measure hallucination rate of state-grounded vs. source-only LLM explanation. |
| O19 | Measure comprehension/debugging outcomes vs. a static-animation control. |

### Explicit non-objectives

Not a production debugger (no native-code stepping, no attach-to-process). Not a general
Python sandbox for hostile adversaries (see `06-sandbox.md` — the honest boundary is
"untrusted student code", not "targeted attacker"). Not a compiler; the IR is a
visualization-oriented representation, not an optimization target.
