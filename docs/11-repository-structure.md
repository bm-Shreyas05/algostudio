# 11 — Repository Structure

*(Deliverable S; §32 of the brief)*

---

## S.1 Layout

```
algostudio/
├── README.md
├── docker-compose.yml
├── Makefile                          # make dev | test | lint | demo | bench
├── docs/                             # this design set (00–19) + ADRs
│   └── adr/                          # accepted architecture decision records
│
├── backend/
│   ├── pyproject.toml
│   ├── algostudio/
│   │   ├── config.py                 # settings (env-driven), paths, feature flags
│   │   │
│   │   ├── core/                     # ── shared vocabulary; stdlib only, zero deps
│   │   │   ├── events.py             # EventType enum, Event, payload builders
│   │   │   ├── values.py             # EncodedValue, HeapObject, ValueEncoder
│   │   │   ├── ir.py                 # IR node dataclasses
│   │   │   ├── source_map.py
│   │   │   └── errors.py             # error taxonomy shared by API + engine
│   │   │
│   │   ├── languages/                # ── the ONLY language-aware layer
│   │   │   ├── base.py               # LanguageFrontend protocol, AnalysisResult
│   │   │   ├── registry.py
│   │   │   └── python/
│   │   │       ├── frontend.py       # orchestrates analyze/instrument
│   │   │       ├── transformer.py    # AST -> instrumented AST  (the core of the engine)
│   │   │       ├── capabilities.py   # SUPPORTED/PARTIAL/UNSUPPORTED classification
│   │   │       ├── lowering.py       # AST -> IR
│   │   │       └── scopes.py         # static binding resolution
│   │   │
│   │   ├── runtime/                  # ── runs INSIDE the sandbox; import-light
│   │   │   ├── probe.py              # the _as_* API called by instrumented code
│   │   │   ├── recorder.py           # value encoding, event serialization, budget
│   │   │   ├── semantic.py           # the `algo` object exposed to user code
│   │   │   ├── policy.py             # import allowlist, builtins denylist
│   │   │   └── child_main.py         # sandbox entrypoint
│   │   │
│   │   ├── sandbox/
│   │   │   ├── base.py               # Sandbox protocol, SandboxPolicy, SandboxResult
│   │   │   ├── subprocess_sandbox.py # dev/Windows; rlimits where available
│   │   │   ├── docker_sandbox.py     # production
│   │   │   └── limits.py             # per-platform limit installation
│   │   │
│   │   ├── state/
│   │   │   ├── model.py              # ExecutionState, Frame, LoopState, Annotation
│   │   │   ├── reducer.py            # R and R' dispatch tables
│   │   │   └── timeline.py           # checkpoints, seek, step, next_matching
│   │   │
│   │   ├── lifters/                  # ── generic events -> semantic events
│   │   │   ├── base.py
│   │   │   ├── pipeline.py
│   │   │   ├── swap.py  compare.py  pointer.py  stackqueue.py  relax.py  region.py
│   │   │
│   │   ├── shapes/                   # ── structure -> view proposals
│   │   │   ├── base.py               # ShapeMatch, Detector protocol
│   │   │   ├── detectors.py
│   │   │   └── resolver.py           # scoring, layout plan
│   │   │
│   │   ├── analytics/
│   │   │   ├── metrics.py            # event folds
│   │   │   └── complexity.py         # fit measured ops against candidate growth curves
│   │   │
│   │   ├── plugins/
│   │   │   ├── base.py               # AlgorithmPlugin, InputField, Complexity, VizHint
│   │   │   ├── registry.py           # filesystem discovery + validation
│   │   │   └── driver.py             # generates the runner module for a plugin
│   │   │
│   │   ├── algorithms/               # ── DATA. Adding one touches nothing else.
│   │   │   ├── binary_search/{plugin.py,source.py,explain.md}
│   │   │   ├── merge_sort/…  bubble_sort/…  bfs/…  dijkstra/…
│   │   │
│   │   ├── ai/
│   │   │   ├── context.py            # AIContext assembly, causal chain
│   │   │   ├── modes.py              # prompt templates per ExplainMode
│   │   │   ├── clients.py            # LLMClient impls (Anthropic, Null)
│   │   │   ├── template.py           # deterministic TemplateExplainer
│   │   │   └── verifier.py           # claim extraction + GroundingReport
│   │   │
│   │   ├── analysis/static.py        # IR-driven program analysis + pattern hints
│   │   ├── inputs/generators.py      # array/graph/matrix/string generators
│   │   │
│   │   ├── store/
│   │   │   ├── db.py                 # sqlite3 schema + thin DAL
│   │   │   └── eventlog.py           # events.jsonl writer/reader + offset index
│   │   │
│   │   ├── services/                 # ── composition; the only place layers meet
│   │   │   ├── execution_service.py  # run pipeline end to end
│   │   │   ├── ai_service.py
│   │   │   └── benchmark_service.py
│   │   │
│   │   └── api/
│   │       ├── app.py                # FastAPI app factory, middleware
│   │       ├── schemas.py            # pydantic DTOs (NOT the engine's dataclasses)
│   │       ├── routes_executions.py  routes_algorithms.py  routes_ai.py
│   │       ├── routes_inputs.py      routes_benchmarks.py  routes_sessions.py
│   │       └── ws.py                 # connection hub
│   │
│   └── tests/
│       ├── unit/            events, values, reducer, transformer, lifters, shapes
│       ├── integration/     end-to-end pipeline, api, websocket
│       ├── security/        adversarial sandbox suite
│       ├── property/        hypothesis: reducer inverse laws, encoder round-trip
│       ├── golden/          committed event logs + expected states
│       ├── fixtures/        .py programs organized by language feature
│       └── bench/           overhead + granularity measurements (feeds §AA)
│
├── frontend/
│   ├── package.json  vite.config.ts  tsconfig.json  index.html
│   └── src/
│       ├── main.tsx  App.tsx  styles.css
│       ├── api/{client.ts,types.ts,ws.ts}      # types.ts mirrors core/events.py
│       ├── engine/{reducer.ts,timeline.ts}     # TS mirror of R/R'; parity-tested
│       ├── store/useExecution.ts               # zustand store
│       ├── components/                         # fixed IDE furniture
│       │   ├── Toolbar.tsx  SourceView.tsx  VariablesPanel.tsx  CallStackPanel.tsx
│       │   ├── Timeline.tsx  ConsolePanel.tsx  AnalyticsPanel.tsx  AIPanel.tsx
│       │   └── CapabilityBanner.tsx  AlgorithmPicker.tsx  InputPanel.tsx
│       ├── views/                              # ── generic renderers; NO algorithm names
│       │   ├── registry.ts
│       │   ├── ArrayView.tsx  MatrixView.tsx  GraphView.tsx  TreeView.tsx
│       │   ├── LinkedListView.tsx  TableView.tsx  SetView.tsx  StackView.tsx
│       │   ├── QueueView.tsx  HeapView.tsx  ObjectView.tsx  CallTreeView.tsx
│       └── lib/{layout.ts,highlight.ts,format.ts}
│
├── shared/
│   ├── schemas/event.schema.json     # generated from core/events.py; the cross-language contract
│   └── scripts/gen_types.py          # event schema -> frontend/src/api/types.ts
│
└── var/                              # runtime data (gitignored)
    └── executions/<id>/…
```

---

## S.2 Responsibility of each major directory

| Directory | Owns | Explicitly forbidden from |
|---|---|---|
| `core/` | The event/value/IR vocabulary. Zero third-party imports. | knowing Python-the-language, HTTP, storage, rendering |
| `languages/` | Parsing, capability classification, IR lowering, instrumentation. **The only place a language is mentioned.** | knowing about storage, views, analytics, or the API |
| `runtime/` | Everything that executes inside the sandbox. | importing FastAPI or anything heavy — it runs in the hostile process |
| `sandbox/` | Process/container isolation, limits, byte transport. | interpreting event semantics |
| `state/` | `R`, `R'`, checkpointing, seek. Pure and deterministic. | I/O, clocks, language knowledge |
| `lifters/` | Recognizing idioms in generic events. | algorithm identity |
| `shapes/` | Structural classification of heap objects into view proposals. | algorithm identity |
| `analytics/` | Folds over events into metrics; growth-curve fitting. | per-algorithm counters |
| `plugins/` | Discovery, validation, driver generation. | rendering |
| `algorithms/` | **Data only.** Metadata + ordinary source. | importing from anywhere in the engine except `plugins.base` |
| `ai/` | Context assembly, prompting, verification. | executing anything |
| `analysis/` | Static, IR-driven program description. | executing anything |
| `store/` | Persistence: SQLite metadata + on-disk event logs. | business logic |
| `services/` | Composition root for use cases. The only layer allowed to import broadly. | being imported by lower layers |
| `api/` | HTTP/WS transport, DTO translation, auth, rate limiting. | business logic |
| `frontend/components/` | Fixed IDE panels. | algorithm identity |
| `frontend/views/` | Generic data-structure renderers. | algorithm identity *(CI-enforced)*, importing from `algorithms/` |
| `frontend/engine/` | TS mirror of the reducer. | diverging from Python *(parity-tested)* |
| `shared/` | The cross-language contract: the event JSON Schema and its codegen. | — |

---

## S.3 Improvements over the structure proposed in the brief

The brief suggested `/backend/{execution,events,languages,visualization,analytics,ai,algorithms}`.
Four changes, each with a reason:

1. **`visualization/` is not a backend directory.** Rendering is a frontend concern. What the
   backend legitimately owns is *view selection*, so that directory became `shapes/`
   (detection) + `resolver` (arbitration). Keeping a `visualization/` folder server-side
   invites rendering logic to migrate into it, which is exactly how "generic renderer"
   projects acquire algorithm-specific branches.

2. **`runtime/` is split out from `execution/`.** The code that runs *inside* the sandbox has
   a completely different dependency budget and threat exposure from the code that
   *orchestrates* the sandbox. Merging them is how a heavy import accidentally ends up in
   the hostile process. The split makes the boundary visible in the file tree.

3. **`lifters/` is a new top-level concern.** The brief's §12 (semantic events) has no home
   in the proposed structure; giving it one is what keeps that logic out of both the
   language frontend and the renderer.

4. **`services/` is added as an explicit composition root.** Without it, `api/` grows business
   logic, and then the engine cannot be used from a CLI or a test without spinning up HTTP.
   Every use case is callable as a plain function.

---

## S.4 Layering rule, enforced

```
core  →  (languages | runtime | state | analytics | plugins | ai | shapes | lifters)
      →  (sandbox | store)
      →  services
      →  api
```

`tests/unit/test_layering.py` parses every module's imports and asserts no upward edge and
no cycles. `algorithms/*` may import only `plugins.base` and the stdlib — asserted
separately, because that rule is INV-1 in mechanical form.
