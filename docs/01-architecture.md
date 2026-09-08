# 01 — Detailed Architecture & Component Architecture

*(Deliverables F, G)*

---

## F. Detailed Architecture

### F.1 Deployment topology

A **modular monolith** with exactly one process boundary that matters: the sandbox.

```
┌──────────────────────────────────────────────────────────────────────┐
│  BROWSER                                                             │
│  React + TypeScript SPA                                              │
│  ├── Editor / SourceView          ├── ViewRegistry (generic renderers)│
│  ├── Timeline / Transport         ├── Analytics panel                 │
│  └── ExecutionStore (client-side reducer mirror)                      │
└───────────────┬────────────────────────────────┬─────────────────────┘
        REST (control, bulk fetch)        WebSocket (live event batches)
┌───────────────▼────────────────────────────────▼─────────────────────┐
│  APPLICATION PROCESS  (FastAPI / uvicorn, single process)            │
│                                                                      │
│  api/          REST routers, WS hub, DTO schemas                     │
│  plugins/      AlgorithmPlugin registry (filesystem discovery)       │
│  languages/    LanguageFrontend registry -> python/ frontend         │
│  sandbox/      SandboxRunner  (Subprocess | Docker)  ── process gate ─┼──┐
│  state/        Reducer, InverseReducer, Timeline (checkpoints)       │  │
│  lifters/      Semantic event lifting pipeline                       │  │
│  shapes/       Structural shape detectors -> ViewDescriptors         │  │
│  analytics/    Event folds -> metrics                                │  │
│  ai/           ContextBuilder -> LLM client -> ClaimVerifier         │  │
│  store/        SQLite (stdlib sqlite3), event log on disk            │  │
└──────────────────────────────────────────────────────────────────────┘  │
                                                                          │
┌─────────────────────────────────────────────────────────────────────────▼┐
│  SANDBOX CHILD  (separate OS process; container in production)           │
│  runtime/child_main.py                                                   │
│   ├── loads instrumented module produced by the frontend                 │
│   ├── probe.py     — the _as_* probe API called by instrumented code     │
│   ├── recorder.py  — encodes values, writes JSONL events to a pipe/file  │
│   ├── semantic.py  — the `algo` object exposed to user code              │
│   └── policy       — import allowlist, builtin denylist, budget guard    │
│  NO network. NO filesystem writes outside its temp dir. Hard budgets.    │
└──────────────────────────────────────────────────────────────────────────┘
```

### F.2 Why a modular monolith

Rejected alternatives and the reason each was rejected:

| Alternative | Why rejected |
|---|---|
| Microservices (execution svc, event svc, AI svc) | The only thing that genuinely needs isolation is *user code execution*, and that is a process/container boundary, not a service boundary. Splitting the rest buys nothing and costs a distributed-tracing problem a 4-person team cannot afford. |
| Kafka / Redis Streams for the event bus | The event stream is **per-execution and bounded** (budget-capped at 200k events, typically <5k). It is a file and an in-memory list, not a distributed log. Kafka would add an operational dependency to move data between two objects in the same process. |
| GraphQL | Access patterns are fixed and known (fetch events page, fetch state at step, ask AI). REST + WS expresses them in fewer moving parts; the flexibility GraphQL buys is unused. |
| Kubernetes | Single-node deployment. `docker compose` is sufficient and reviewable. |
| Postgres for MVP | SQLite handles the metadata volume trivially; the *event log* is not in the database at all (see F.4). The schema is plain portable SQL, so Postgres is a driver swap when multi-user concurrency arrives. |

The one place we *do* pay for indirection is the sandbox: user code must never run in the
API process. That boundary is non-negotiable and is discussed in `06-sandbox.md`.

### F.3 The control flow of one execution

```
1.  POST /api/v1/executions  {language:"python", source, inputs, options}
2.  LanguageFrontend.analyze(source)
      -> parse to AST
      -> CapabilityChecker: classify every construct SUPPORTED/PARTIAL/UNSUPPORTED
      -> if any UNSUPPORTED and options.strict -> 422 with a precise diagnostic
      -> lower to IR (for static analysis, source map, and future languages)
3.  LanguageFrontend.instrument(ast, granularity)
      -> InstrumentedProgram {code_object, source_map, probe_manifest}
4.  SandboxRunner.run(program, inputs, policy)
      -> spawn child; child streams JSONL events to an event file
      -> server tails the file, pushing batches over WS as they arrive
      -> child exits (normally / budget-exceeded / killed)
5.  LifterPipeline.process(raw_events) -> events (raw + lifted semantic events)
6.  Timeline.build(events)
      -> forward-fold with Reducer, checkpoint every K steps
      -> Analytics fold in the same pass
7.  Persist: execution row (SQLite) + events.jsonl + checkpoints (on disk)
8.  Client navigates: GET /state?step=n  -> Timeline.state_at(n)
9.  Client asks AI:   POST /ai  -> ContextBuilder(state_at(n), window(events,n))
                                -> LLM -> ClaimVerifier -> answer + grounding report
```

Steps 5–6 are a **single post-run pass**; they are also runnable incrementally so the UI
can navigate a still-running execution. See `03-state-and-time-travel.md`.

### F.4 Storage split (an important decision)

Execution **metadata** goes in SQLite. Execution **events** do not.

Rationale: the event log is append-only, read sequentially or by index range, never
queried relationally, and can reach tens of MB. Putting it in rows costs a 10–50x
serialization overhead for zero benefit. Events are stored as `events.jsonl` (optionally
gzip) under `var/executions/<id>/`, with a sidecar `index.bin` of `uint64` byte offsets
so `events[i]` is an O(1) seek. Checkpoints are `checkpoints/<step>.json`.

This also means an execution is **portable**: the directory is the execution. Sharing a
session is copying a directory.

---

## G. Component Architecture

Each component below states its **responsibility**, its **inbound contract**, its
**outbound contract**, and — critically — **what it is forbidden from knowing**. The
"forbidden" column is what enforces INV-1 and INV-2.

### G.1 `core/` — shared vocabulary

| | |
|---|---|
| Responsibility | Event dataclasses + `EventType` enum, value/heap encoding (`EncodedValue`, `HeapObject`), IR node types, error taxonomy. |
| In | nothing (leaf module) |
| Out | types imported by everyone |
| Must not know | anything about Python, algorithms, HTTP, or rendering |

`core` is deliberately dependency-free (stdlib only). It is the schema both the sandbox
child and the server agree on, and it is the thing a future C++ frontend must satisfy.

### G.2 `languages/` — language frontends

| | |
|---|---|
| Responsibility | `SourceText -> (IR, InstrumentedProgram, SourceMap, CapabilityReport)` |
| In | source text, granularity policy |
| Out | `core` types only |
| Must not know | how events are stored, rendered, analysed, or explained |

Interface (`languages/base.py`):

```python
class LanguageFrontend(Protocol):
    language_id: str
    file_extensions: tuple[str, ...]
    def analyze(self, source: str) -> AnalysisResult: ...      # AST, IR, capabilities
    def instrument(self, source: str, opts: InstrumentOptions) -> InstrumentedProgram: ...
    def runtime_bootstrap(self) -> str: ...                     # child-side loader
```

Python is the MVP implementation. `07`, `26` in the brief map onto adding a new class here
and nothing else. A `CppFrontend` would produce the *same* `Event` stream — likely via
a different mechanism (source-to-source instrumentation or a gdb/MI driver) — and every
component downstream is unchanged. That is the entire point of INV-2.

### G.3 `runtime/` — the in-sandbox library

| | |
|---|---|
| Responsibility | Provide `_as_*` probes called by instrumented code; encode values; serialize events; enforce the execution budget; expose the `algo` semantic API to user code. |
| In | calls from instrumented user code |
| Out | JSONL on the event channel |
| Must not know | the server, the database, HTTP, or which algorithm is running |

This module is copied/imported *inside the sandbox*. It must be import-light and must not
depend on FastAPI, a database driver, or anything that would enlarge the sandbox's attack
surface. It depends only on `core` (for the event schema) and stdlib.

### G.4 `sandbox/` — isolation

| | |
|---|---|
| Responsibility | Run an `InstrumentedProgram` under a `SandboxPolicy`, return `(events_path, stdout, exit_status, resource_usage)`. |
| In | program + policy |
| Out | event file path + termination reason |
| Must not know | event *semantics*; it moves bytes and enforces limits |

Two implementations behind one interface: `SubprocessSandbox` (dev, Windows-compatible)
and `DockerSandbox` (production). Policy is data, not code.

### G.5 `state/` — reducer, inverse reducer, timeline

| | |
|---|---|
| Responsibility | `R`, `R'`, checkpointing, `state_at(n)`, `step_forward`, `step_back`, `seek`. |
| In | `[Event]` |
| Out | `ExecutionState` |
| Must not know | the language, the algorithm, or the renderer |

The reducer is a **pure total function** with a dispatch table keyed on `EventType`. Adding
an event type adds a table entry; it never adds a branch anywhere else.

### G.6 `lifters/` — semantic event lifting

| | |
|---|---|
| Responsibility | Recognize patterns in the low-level event stream and emit higher-level `ALGORITHM_*` events (e.g. three writes forming a swap -> `SWAP`). |
| In | `[Event]`, sliding window |
| Out | additional `[Event]` interleaved by `logical_step` |
| Must not know | which algorithm is running — lifters match on **structure**, not identity |

This is the answer to §12 of the brief. A lifter is a small state machine over generic
events; it never sees an algorithm name. `SwapLifter` fires on *any* pair of subscript
writes to the same container that exchange values, whether it happens inside bubble sort,
a partition step, or a student's own code.

### G.7 `shapes/` — structural detection

| | |
|---|---|
| Responsibility | Inspect a `HeapObject` and produce scored `ViewDescriptor`s ("this dict-of-lists is an adjacency list, confidence 0.86"). |
| In | `ExecutionState` heap |
| Out | `[ViewDescriptor]` |
| Must not know | algorithm identity |

Detectors are ranked, additive, and pluggable. A plugin may supply a `visualization_hint`
which **biases the score**; it can never force a view. This preserves the property that
the same code typed by a student gets the same visualization as the packaged plugin.

### G.8 `analytics/` — metric folds

Pure folds over the event stream: statements executed, comparisons, swaps, array reads /
writes, function calls, max recursion depth, per-line hit counts, wall/CPU time,
peak encoded heap size. Algorithm-specific counters (Dijkstra's *edges relaxed*) are
**not special-cased** — they are counts of `ALGORITHM_EVENT` subtypes that either the
lifters or the user's own `algo.*` calls produced.

### G.9 `plugins/` + `algorithms/` — the plugin system

| | |
|---|---|
| Responsibility | Discover, validate, and describe algorithm plugins. |
| In | filesystem scan of `algorithms/*/plugin.py` |
| Out | `AlgorithmPlugin` records |
| Must not know | anything about rendering |

A plugin is **metadata + a plain source file**. The source file is executed by the *same*
engine that runs user code — there is no privileged path. See `07-plugin-architecture.md`.

### G.10 `ai/` — grounded explanation

| | |
|---|---|
| Responsibility | Build a bounded, typed context from real state; call an LLM; verify claims against state. |
| In | `ExecutionState`, event window, question, mode |
| Out | answer + `GroundingReport` |
| Must not know | how to execute anything |

Includes a deterministic **template explainer** used (a) when no API key is configured and
(b) as the experimental baseline in RQ3.

### G.11 `api/` — transport

Thin. Routers translate DTOs to service calls. No business logic. WS hub fans out event
batches per execution id.

### G.12 Frontend components

| Component | Depends on | Forbidden |
|---|---|---|
| `ExecutionStore` (zustand) | REST/WS DTOs | knowing algorithms |
| `SourceView` | source map + `current_line` | knowing algorithms |
| `VariablesPanel`, `CallStackPanel` | `ExecutionState` | knowing algorithms |
| `Timeline` | `[EventSummary]` | knowing algorithms |
| `ViewRegistry` + `views/*` | `ViewDescriptor` + heap slice | **knowing algorithms** (lint-enforced) |
| `AnalyticsPanel` | `Analytics` | — |
| `AIPanel` | `/ai` responses | — |

`frontend/src/views/**` is checked by a test that greps for algorithm names
(`bubble`, `dijkstra`, `bfs`, `merge`, `binary_search`, ...). A non-zero match fails CI.
That test is the mechanical statement of the project's central claim.

---

## G.13 Dependency direction (acyclic)

```
core  <—  languages  <—  sandbox
  ^           ^
  |           |
  +——  runtime (in-child)
  ^
  +——  state  <—  lifters
  ^        ^
  |        +——  shapes
  +——  analytics
  ^
  +——  ai
  ^
  +——  plugins  <—  algorithms (data only)
  ^
  +——  api  ——> everything above (composition root)
```

`api` is the only module allowed to import from more than one layer. Enforced by
`tests/test_layering.py`, which parses imports and asserts the DAG.
