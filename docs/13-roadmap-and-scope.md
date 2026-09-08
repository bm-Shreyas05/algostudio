# 13 — Implementation Roadmap & Scope

*(Deliverables W, X; §39–§41 of the brief)*

---

## W. Implementation Roadmap

Sequenced so that **the riskiest thing is built first** and every phase ends with something
demonstrable. The ordering principle: nothing downstream can be validated until the event
stream exists, so the event stream comes first, and the two highest-risk components
(transformer, sandbox) are front-loaded rather than left to integration week.

| Phase | Weeks | Deliverable | Exit criterion (binary, testable) |
|---|---|---|---|
| **P0 — Contract** | 1 | `core/`: `EventType`, `Event`, `EncodedValue`, `HeapObject`, JSON Schema, error taxonomy | round-trip serialization property test passes; schema published to `shared/` |
| **P1 — Tracer spike** | 1–2 | `transformer.py` for: assignment, `if`, `while`, `for`, functions, `return`, subscripts | `x=5; for i in range(5): x+=i` produces the exact event sequence in `02-event-model.md` §H.6; **differential test** (instrumented vs native output) green on 20 fixtures |
| **P2 — Sandbox** | 2–3 | `SubprocessSandbox`, budget guard, import/builtin policy, event file + index | adversarial suite cases 1–7, 9, 11 pass on Windows and Linux |
| **P3 — Reducer & time travel** | 3–4 | `state/`: `R`, `R'`, `Timeline`, checkpoints | `unapply(apply(s,e),e) == s` property test; `state_at(n)` ≡ full forward replay for all n on all fixtures |
| **P4 — Vertical slice UI** | 4–6 | React shell, `SourceView`, `VariablesPanel`, `CallStackPanel`, `Timeline`, `ConsolePanel`, TS reducer mirror | step forward/backward through a real program in the browser; reducer-parity test green |
| **P5 — Views & shapes** | 6–7 | `shapes/` detectors + resolver; `ArrayView`, `TableView`, `ObjectView`, `CallTreeView` | binary search shows an array with pointers; `fib(5)` shows a recursion tree — **without any algorithm-specific code** |
| **P6 — Plugins** | 7–8 | `plugins/`, driver, Binary Search + Merge Sort | INV-1 test passes: adding Merge Sort touched only its own directory |
| **P7 — Semantics** | 8–9 | `algo` API, lifter pipeline, `SwapLifter`, `CompareLifter`, `PointerLifter`, `StackQueueLifter` | unannotated bubble sort produces `SWAP` events; swap animation works from lifted events alone |
| **P8 — Graphs** | 9–10 | `GraphView`, `AdjacencyMap` detector, BFS + Dijkstra plugins, `RelaxLifter` | BFS on a student-typed adjacency dict renders a graph with visited marks, zero graph-specific backend code |
| **P9 — Analytics & benchmarking** | 10–11 | `analytics/`, complexity fit, `/benchmarks`, comparison view | Merge vs Bubble on n = 50/100/200/400 produces measured curves |
| **P10 — AI** | 11–12 | `ai/`: context, causal chain, modes, `TemplateExplainer`, Anthropic client, verifier | "why did mid become 4" answered correctly, grounding score 1.0, and correctly answered with the LLM disabled |
| **P11 — Hardening** | 12–13 | `DockerSandbox`, capability banner, error paths, persistence, session sharing | full adversarial suite in Docker mode; a killed run is still navigable |
| **P12 — Evaluation** | 13–15 | Overhead benchmarks, plugin-effort study, AI grounding study, user study | data collected per `15-research-and-evaluation.md`; results written up honestly including negatives |
| **P13 — Delivery** | 15–16 | Report, slides, demo script, video, repo hygiene | full demo runs from a clean checkout in under 5 minutes |

### Critical path and parallelism

```
P0 ──► P1 ──► P3 ──► P4 ──► P5 ──► P6 ──► P7 ──► P8 ──► P9 ──► P12
        └──► P2 ──────────────────────────────────► P11
                              └──► P10 ────────────────► P12
```

P2 (sandbox) is parallel to P3/P4 after P1. P10 (AI) can start once P3 exists, since it
consumes state. P5 onwards is frontend-heavy and runs alongside backend work.

### Sequencing rules the team must hold to

1. **No view work before the reducer is correct.** A pretty view over a wrong state is worse
   than no view, and it hides reducer bugs behind plausible pictures.
2. **No algorithm plugin before the plugin interface is frozen.** Otherwise the interface is
   retrofitted to the four algorithms we happened to write, and INV-1 silently dies.
3. **The differential test (P1) is a gate, not a task.** If instrumented code behaves
   differently from native code, everything built on top is measuring a fiction.
4. **AI last among features.** It is the most visible and least load-bearing; building it
   early distorts priorities and produces a demo that hides an empty engine.

---

## X. Scope: MVP / V2 / V3

### MVP (this deliverable)

**Language subset** — see `19-capability-matrix.md` for the tested boundary.
Variables · arithmetic and comparison · `if/elif/else` · `while` · `for` over
`range`/list/str/dict/set/`enumerate`/`zip` · `break`/`continue` · functions with
positional/default/`*args`/`**kwargs` · recursion · lists, tuples, dicts, sets, strings ·
subscripts and slices · list/dict methods · `try/except/finally` · `raise` · classes
(construction, attributes, methods — **partial**, no multiple inheritance/metaclasses) ·
imports from the allowlist.

**Engine** — AST instrumentation at three granularities · event stream (40+ types) ·
subprocess sandbox with budgets · reducer + inverse reducer · checkpointed timeline ·
lifter pipeline (swap, compare, pointer, stack/queue, relax) · shape detection + view
resolution · analytics folds.

**UI** — source view with current line / executed-line heat / branch marks · variables with
change highlighting and aliasing arrows · call stack · timeline with loop and call grouping ·
console (time-scrubbed) · array, table, set, stack/queue, graph, tree, object, call-tree
views · analytics panel · AI panel · capability banner.

**Navigation** — step forward/back, play/pause/speed, restart, jump to step, replay,
step over/into/out, replay-side line breakpoints.

**Content** — Binary Search, Merge Sort, BFS, Dijkstra (+ Bubble Sort for comparison) ·
input generators (array distributions, random graphs) · basic benchmarking.

**AI** — grounded explanation with causal chains, 10 modes, claim verifier,
`TemplateExplainer` offline mode.

**Explicitly out of MVP:** graph/tree *editors* (input is JSON/text), live pause-and-modify
of a running program, multi-file projects, user accounts and auth (single-tenant local
mode), collaborative features, C++/Java/JS.

### V2

| Feature | Why it is V2, not MVP |
|---|---|
| Graph / tree visual editors | pure UI work, large surface, adds no architectural evidence |
| Synchronized side-by-side algorithm comparison | needs a second timeline cursor and a step-alignment heuristic; valuable but not load-bearing |
| Conditional & data breakpoints (`when arr[i] > x`) | needs a safe expression evaluator over `ExecutionState` |
| **Live sandbox control** (true pause/resume/modify) | needs a bidirectional control channel into the child and a state-mutation protocol; genuinely hard, and the replay approximation covers the teaching need |
| Comprehension / lambda / `with` fine instrumentation | scope-correctness work with a real test burden |
| Warm container pool | performance work, only matters at deployment scale |
| Accounts, projects, session sharing, classroom rosters | product work, not engine work |
| Custom user-authored lifters | needs a safe DSL or a plugin trust model |
| Static algorithm-pattern detection surfaced in the UI | the IR support exists in MVP; the UX and the confidence calibration are V2 |
| Export: GIF/video/PDF of an execution | requested by instructors, purely additive |

### V3

| Feature | Prerequisite |
|---|---|
| **C++ frontend** | source-to-source instrumentation via libclang emitting the same event schema; the real test of INV-2 |
| **Java frontend** | JVMTI agent or bytecode instrumentation (ASM) emitting the schema |
| **JavaScript frontend** | Babel plugin — architecturally the easiest, and the one that could run entirely client-side |
| Client-side Python via Pyodide/WASM | removes the server threat surface entirely; changes the sandbox story fundamentally |
| Automatic visualization *suggestion* learned from usage | needs telemetry and a labelled corpus |
| Collaborative classroom mode (shared cursor on a timeline) | needs multi-user infrastructure |
| Cross-language execution comparison (same algorithm, Python vs C++, one timeline) | needs two frontends and a step-alignment model — the most compelling long-term demo of the architecture |
| Cloud execution at classroom scale | queueing, autoscaling, per-tenant quotas |

### Deliberate scope refusals

Stated so they do not creep back in:

- **No general Python support claim.** The capability matrix is the contract.
- **No hand-authored per-algorithm animations.** If a view cannot be derived, we report that
  as a finding rather than special-casing it.
- **No "AI generates the visualization".** The LLM explains; it does not decide what is drawn.
  A hallucinated visualization is unfalsifiable, which defeats the project's premise.
- **No multi-language MVP.** One language done properly is evidence; three done shallowly is not.
