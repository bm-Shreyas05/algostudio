# 18 — Team Work Breakdown & Risk Register

*(Deliverables AH, AI)*

---

## AH. Team Member Work Breakdown

Assumes a **4-person team over 16 weeks**. Scaling notes for 2 and 3 are at the end.

The allocation principle: each member owns one **vertical** through the architecture so
that everyone integrates continuously, plus one **horizontal** specialism they are the
authority on. Splitting purely horizontally (one person "does backend") produces three
people blocked on one, and a report where only one member can answer questions in the viva.

### Member A — Execution Engine Lead *(highest risk, most senior)*

| Owns | Deliverables |
|---|---|
| `languages/python/` — transformer, capabilities, lowering, scopes | the AST transformer and every rule in `05-K.4` |
| `core/` — event and value model | `EventType`, `Event`, `EncodedValue`, JSON Schema |
| `runtime/` — probes, recorder, semantic API | the in-sandbox library |
| Tests | differential semantic-preservation suite, transformer unit tests, property tests |
| Report | Ch 4.2, 4.4, 4.5; Ch 5.3 |
| Presentation | slides 5, 7 |

*Why this is one person:* the transformer and the event model must be designed together;
splitting them produces an event model that the transformer cannot populate.

### Member B — Runtime, Sandbox & Platform

| Owns | Deliverables |
|---|---|
| `sandbox/` — subprocess + Docker, limits, budget guard | both implementations, the policy model |
| `store/` — SQLite, event log, offset index, checkpoint persistence | persistence layer |
| `api/` — REST routers, WS hub, rate limiting | full API surface |
| `services/` — execution pipeline composition | the orchestration |
| DevOps | Docker Compose, CI pipeline, Makefile, deployment guide |
| Tests | adversarial security suite, API + WS integration tests |
| Report | Ch 4.6, 4.10, 4.11; Ch 5.8; Ch 6 (security results) |
| Presentation | slides 6, 8 |

### Member C — State, Semantics & Analytics

| Owns | Deliverables |
|---|---|
| `state/` — reducer, inverse reducer, timeline, checkpoints | `R`, `R'`, seek strategy |
| `lifters/` — the semantic lifting pipeline | swap, compare, pointer, stack/queue, relax, region |
| `shapes/` — detectors and the view resolver | detection + scoring |
| `analytics/` — folds, complexity fitting | metrics + growth-curve fit |
| `plugins/` + `algorithms/` — registry and the 5 reference plugins | plugin system |
| Tests | reducer property tests, time-travel equivalence, lifter precision/recall, detector corpus |
| Report | Ch 4.3, 4.7, 4.8; Ch 5.4–5.6 |
| Presentation | slides 9, 11 |

### Member D — Frontend, AI & Evaluation

| Owns | Deliverables |
|---|---|
| `frontend/` — the whole SPA | panels, views, TS reducer mirror, store |
| `ai/` — context, causal chain, modes, verifier, clients | grounded explanation |
| `inputs/` — generators | array/graph/matrix generators |
| Research instruments | study protocols, quizzes, TLX forms, analysis notebooks |
| Tests | component tests, reducer-parity, Playwright E2E, verifier tests |
| Report | Ch 4.9, 5.7; Ch 7 (results); Appendix D |
| Presentation | slides 10 (demo), 12, 13 |

*Frontend is one person's full plate.* If the team has frontend strength to spare, split
`views/` (the generic renderers) from `components/` (the IDE panels) — they share only the
store and are cleanly separable.

### Shared / rotating

| Item | Owner |
|---|---|
| Literature survey (Ch 2) | all four, 3 topics each from `15-AD` |
| Weekly integration + demo | rotating |
| Code review | every PR needs one reviewer who does not own the module |
| Report editing pass | Member A (technical), Member D (results) |

### Timeline by member

```
Week    1   2   3   4   5   6   7   8   9  10  11  12  13  14  15  16
A     [core ][ transformer ][ transformer++ ][ capabilities ][ fixes ][ report ]
B     [ core][ sandbox     ][ store  ][ api      ][ ws  ][ docker ][ hard ][ report ]
C          [ reducer ][ timeline ][ shapes ][ plugins ][ lifters ][ analytics ][ report ]
D               [ ui shell ][ panels ][ views      ][ graph/tree ][ ai   ][ eval  ][ report ]
                                                                  ^ P10   ^ P12
Integration demo every Friday from week 4. Feature freeze week 13.
```

### Smaller teams

- **3 people:** merge B and C's analytics/plugins into B; C keeps state + lifters + shapes.
  Drop Docker sandbox to "documented + Dockerfile only", drop the RQ2 user study to a
  6-person pilot.
- **2 people:** one owns engine + sandbox (A+B), one owns state + frontend + AI (C+D).
  Cut to 3 reference algorithms, drop benchmarking UI, drop RQ2 entirely and keep RQ1/RQ3/RQ4
  (all automatable). The architecture does not change — only the scope does.

---

## AI. Risk Register

Scored `Probability × Impact` on 1–5. **Exposure = P×I.** Ordered by exposure.

| # | Risk | P | I | Exp | Why it is risky | Mitigation | Trigger / fallback |
|---|---|---|---|---|---|---|---|
| **R1** | **AST transformer changes program semantics** | 4 | 5 | **20** | A subtly wrong transform (evaluation order, short-circuit, single-evaluation) produces a *plausible but false* trace. The tool would then teach wrong things, and the failure is silent | Differential execution test as a **merge gate** from week 2; random program generation; conservative fallback per construct; `INSTRUMENTATION_SKIPPED` rather than guessing | If a construct resists a safe transform for > 2 days, downgrade it to statement-level and record it in the capability matrix |
| **R2** | **Scope explosion** — the brief describes ~3 years of work | 5 | 4 | **20** | Every section of the brief is individually reasonable. Together they are not achievable in 16 weeks | MVP/V2/V3 split is contractual, not aspirational; feature freeze at week 13; "is this in `13-X` MVP?" is the answer to every proposal | Weekly scope review; anything new displaces something existing, explicitly |
| **R3** | Event volume makes large programs unusable | 4 | 4 | 16 | 1M-event traces break the browser and the reducer | Budget cap (200k); granularity levels; server-side state above `MAX_CLIENT_EVENTS`; timeline virtualization; loop-group collapsing | If the demo corpus exceeds 50k events at `standard`, lower the default granularity |
| **R4** | Automatic view resolution picks the wrong view | 4 | 3 | 12 | A dict-of-lists that is not a graph rendered as a graph looks broken and undermines the core claim | Confidence scores + "why this view" tooltip + user override + `alternatives` list; labelled detector corpus with measured precision | If precision < 80% on the corpus, default to the generic view and make specialized views opt-in per object |
| **R5** | Time-travel state diverges from real execution | 3 | 5 | 15 | An inverse-reducer bug shows a state that never existed — worse than a crash | `SNAPSHOT` verification mode in CI; property tests; `state_at(n)` ≡ full replay for all n on all fixtures | Any divergence is a P0 stop-the-line bug |
| **R6** | Sandbox escape or resource exhaustion in a public deployment | 3 | 5 | 15 | Real consequences beyond the project | Documented threat model; Docker mode mandatory for any multi-user deployment; adversarial suite in CI; rate limits | Default deployment posture is single-user localhost |
| **R7** | Team member unavailable (illness, placement, exams) | 4 | 3 | 12 | Single-owner modules stall | Cross-review requirement means ≥ 2 people have read every module; docs-first design; weekly integration keeps `main` demo-able | Re-allocate using the 3-person plan |
| **R8** | LLM API cost, rate limits, or unavailability | 3 | 3 | 9 | Demo failure, budget overrun | `TemplateExplainer` is fully functional offline; response caching; per-session cap; AI is architecturally optional | Demo runs with AI disabled if needed |
| **R9** | Frontend complexity underestimated | 4 | 3 | 12 | 12 view components + a reducer mirror + a virtualized timeline is a lot for one person | Ship 4 views first (array, table, object, call-tree); graph/tree in P8; strict `ViewProps` contract makes views independent and parallelizable | Drop `HeapView`, `LinkedListView`, `MatrixView` to V2 |
| **R10** | User study cannot recruit enough participants | 4 | 2 | 8 | RQ2 unanswerable | RQ1, RQ3, RQ4, RQ5-quantitative need **zero** participants — the project's evaluation does not depend on recruitment | Report RQ2 as a pilot with n reported honestly, or as future work |
| **R11** | Windows/Linux behaviour divergence | 3 | 2 | 6 | `rlimit` and process groups are POSIX-only; the team develops on Windows | `policy_applied` records what was actually installed; CI on both; Docker mode via WSL2 | Documented as a known dev-mode limitation |
| **R12** | Reducer parity (Python vs TypeScript) drifts | 3 | 3 | 9 | Client and server disagree about state | Parity test in CI on every fixture; single event-type table drives both | If drift is chronic, drop the client reducer and use server-side `state_at` everywhere (costs latency, buys correctness) |
| **R13** | Lifters produce false positives | 3 | 3 | 9 | A fake `SWAP` is a lie about the program | Negative test cases; confidence on every lifted event; `meta.origin` shown in the UI; lifters can be disabled entirely | If precision < 90%, raise thresholds and accept lower recall — a missed swap is far better than an invented one |
| **R14** | Integration left too late | 2 | 5 | 10 | Classic student-project failure: four working modules that have never met | Weekly Friday integration demo from week 4; `main` must always run the demo | A Friday where the demo does not run stops feature work until it does |
| **R15** | Report/presentation rushed | 3 | 4 | 12 | Excellent engineering, mediocre grade | Docs written *before* code (this document set is the evidence); Ch 2 and Ch 4 drafted by week 8; results chapter is a template with empty tables from week 1 | Feature freeze at week 13 exists for this reason |
| **R16** | Over-claiming in the report | 3 | 4 | 12 | "Visualizes any Python" is falsifiable in 30 seconds by an examiner | Capability matrix is a chapter and an appendix; §46 language used throughout; the honest comparison in `16` | Any sentence containing "any code" or "all algorithms" is rewritten in review |

### Top-3 watch list

**R1, R2, R5.** Each can invalidate the project rather than merely delay it: R1 makes the
output untrustworthy, R2 makes it unfinished, R5 makes the headline feature a lie. The
weekly review checks these three explicitly, and each has an automated test that must be
green on `main` at all times.

### Contingency ladder

If the project is behind at **week 10**, cut in this order — each cut is chosen to preserve
the architectural claim while shedding surface area:

1. Docker sandbox → subprocess only, Dockerfile documented (loses deployment realism)
2. Benchmark comparison UI → CLI script producing a CSV (loses polish)
3. Dijkstra plugin → BFS alone covers graphs (loses one demo)
4. `HeapView`, `MatrixView`, `LinkedListView` → V2 (loses breadth)
5. RQ2 user study → 6-person pilot (loses statistical power)
6. AI LLM client → `TemplateExplainer` only (loses a slide, keeps the grounding argument)

**Never cut:** the reducer's inverse, the differential semantic-preservation test, the
capability matrix, or the custom-algorithm demo (Scenario 7). Those four *are* the project.
