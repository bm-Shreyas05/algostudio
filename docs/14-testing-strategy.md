# 14 — Testing Strategy

*(Deliverable Y; §33 of the brief)*

---

## Y.1 What must be true, and how each is proven

The test suite is organized around **claims**, not around modules. Each claim maps to a
mechanism; if the mechanism cannot fail the build, the claim is not actually being tested.

| # | Claim | Mechanism | File |
|---|---|---|---|
| 1 | Instrumentation does not change program behaviour | **differential execution**: run native vs instrumented, compare stdout, return value, exception type/message | `test_semantic_preservation.py` |
| 2 | The reducer is exactly invertible | property test: `unapply(apply(s,e),e) == s` over generated events and over all recorded fixtures | `property/test_reducer_inverse.py` |
| 3 | Time travel is correct | for every fixture and every n: `timeline.state_at(n)` == naive full forward replay to n | `test_time_travel.py` |
| 4 | Server and client reducers agree | run fixtures through Python reducer; run the same events through the TS reducer under Node; compare canonical JSON | `test_reducer_parity.py` |
| 5 | The sandbox contains hostile programs | 12 adversarial cases with *specific required outcomes* | `security/test_sandbox.py` |
| 6 | Adding an algorithm touches no core file | path manifest: import the plugin, assert the module set loaded from `algorithms/` is disjoint from core; plus a `git diff --name-only` check in the PR template | `test_plugin_isolation.py` |
| 7 | Views contain no algorithm knowledge | source grep tripwire + import-graph check on `frontend/src/views/**` | `test_no_algorithm_names_in_views.py` |
| 8 | The layer DAG has no upward edges or cycles | AST-parse every module's imports, assert against the declared layer order | `test_layering.py` |
| 9 | A packaged plugin and the same code pasted by a user produce the same events | run both, compare event streams modulo module name and timestamps | `test_plugin_source_parity.py` |
| 10 | The event schema is backward compatible | replay committed golden logs from earlier schema versions | `golden/test_replay_golden.py` |
| 11 | The AI never asserts unverified runtime facts | run the mode suite against fixtures with a stub LLM that deliberately hallucinates; assert the verifier flags it | `test_ai_verifier.py` |
| 12 | Unsupported constructs degrade, never crash or lie | for each unsupported construct: assert execution completes, `INSTRUMENTATION_SKIPPED` is emitted with the right line, and the capability report names it | `test_capability_degradation.py` |

Claims 1, 2, 5, 6, 7 are the load-bearing ones. If any of them fails, the project's thesis
is false, so they run on every commit and are never marked xfail.

---

## Y.2 Unit tests

### Event & value layer
- `EventType` completeness: every enum member has a reducer handler **and** an inverse
  handler (or is explicitly registered as non-mutating). A new event type without a handler
  fails the test — this is what keeps `R` total by construction.
- `ValueEncoder`: primitives, nested containers, cycles (`a = []; a.append(a)`), depth
  truncation, length truncation, `str` truncation, unencodable objects → `opaque`,
  ref stability (same object → same ref), ref uniqueness.
- JSON round-trip: `Event.from_json(e.to_json()) == e` (hypothesis-generated).

### Transformer (the largest unit suite)
One test per rule in `05-python-execution-strategy.md` §K.4, each asserting the emitted
event sequence, plus:
- `lineno`/`col_offset` preservation for every node kind
- evaluation-order preservation: `a[f()] = g()` calls `g` before `f`
- short-circuit preservation: `False and boom()` does not raise
- single evaluation: `a[f()] += 1` calls `f` exactly once
- generator laziness: `for x in infinite_gen()` is stopped by budget, not by materialization
- `global`/`nonlocal` still bind correctly after probe insertion
- decorators, default args, and annotations are untouched
- `break`/`continue`/`return`/exception all produce `LOOP_FINISHED` with the right `exit`

### Reducer
Per event type: forward effect, inverse effect, idempotence of non-mutating events,
unknown-event-type no-op, `stdout` truncation inverse, counter decrement inverse.

### Lifters
Positive cases (each idiom in all its spellings — tuple swap, temp-variable swap,
`list.__setitem__` pairs), and **negative cases**, which matter more: two adjacent writes
that are *not* a swap must not produce `SWAP`. False-positive rate on the fixture corpus is
recorded as a metric, not just asserted.

### Shape detectors
A labelled corpus of ~60 heap objects with expected view + minimum score, including
adversarial ones: an empty list, a dict-of-lists that is *not* a graph (keys not referenced
in values), a numeric list that accidentally satisfies the heap property, a linked structure
with a cycle.

### Analytics
Hand-counted expectations on small fixtures (bubble sort on `[3,1,2]` has exactly 3
comparisons and 2 swaps), so the counters are checked against arithmetic rather than against
themselves.

---

## Y.3 Integration tests

| Scenario | Asserts |
|---|---|
| Full pipeline on each of ~40 fixture programs | status, event count within bounds, final state matches an expected snapshot |
| `POST /executions` → WS → `finished` → `GET /state` | events streamed live match the persisted file exactly |
| WS reconnect mid-run with `from_event=n` | no gaps, no duplicates |
| Cancel a running execution | child dies, partial events persisted, status `killed` |
| Cache hit | second identical `POST` returns `cached: true` and does not spawn a child |
| Plugin run vs pasted source | claim 9 |
| Benchmark of 2 algorithms × 4 input sizes | 8 executions, metrics monotone in n |
| AI endpoint with `NullClient` | `TemplateExplainer` answer, grounding score 1.0 |
| Docker sandbox mode (CI on Linux only) | full adversarial suite passes with container limits asserted |

---

## Y.4 Fixture corpus

`tests/fixtures/` organized by the thing being exercised, because the capability matrix is
generated from it — every row in `19-capability-matrix.md` has at least one fixture, and a
row without one fails a meta-test.

```
fixtures/
├── basics/        assignment, augassign, multi-target, swap, del, chained compare
├── control/       if/elif/else, while, for-range, for-collection, nested, break,
│                  continue, for-else, while-else
├── functions/     args, defaults, *args/**kwargs, closures, nonlocal, global,
│                  recursion, mutual recursion, deep recursion, generators(*)
├── data/          list, dict, set, tuple, str ops, slicing, nested containers,
│                  aliasing, mutation via methods, sort/reverse, heapq, deque
├── classes/       simple class, methods, inheritance, dunder methods(*)
├── errors/        ZeroDivision, IndexError, KeyError, custom exception, try/finally,
│                  re-raise, uncaught (must still produce a navigable trace)
├── algorithms/    the 5 reference algorithms + 6 student-written ones
├── pathological/  infinite loop, deep recursion, huge allocation, huge output,
│                  self-referential structure, 200k-event program
└── unsupported/   async, threading, comprehension detail, match, walrus-in-comp,
                   eval/exec, file I/O, network
```

`(*)` = expected PARTIAL; the fixture asserts *degradation*, not success.

`unsupported/` fixtures assert the **graceful-failure contract**: the run completes, the
capability report names the construct and line, and the UI banner would show it. A crash
there is a bug of equal severity to a wrong result.

---

## Y.5 Property-based tests (hypothesis)

1. **Reducer inverse law** — generate random valid event sequences from a state machine that
   only emits well-formed events; assert `unapply ∘ apply = id` and that forward replay
   from 0 equals checkpoint-based `state_at` for random n.
2. **Encoder round-trip** — generate arbitrary nested JSON-able Python values (bounded);
   assert encode → decode preserves structure up to declared truncation.
3. **Timeline seek** — random walk of step/seek/back operations; assert the state always
   equals the reference full-replay state. This is the test most likely to find a real bug,
   because it explores operation *interleavings* a human would not write.
4. **Transformer idempotence of semantics** — generate small random programs from a grammar
   over the supported subset; assert claim 1 (differential execution) on each. Random
   program generation is how we find the evaluation-order bugs we did not think of.

---

## Y.6 Frontend tests

- **Component (Vitest + Testing Library):** each view renders from a fixture
  `(HeapObject, annotations)` without touching the network; `ArrayView` shows pointers at
  the right indices; `GraphView` places every node exactly once; `TreeView` handles an
  unbalanced tree.
- **Reducer parity (claim 4):** the highest-value frontend test.
- **Store:** step/seek/play transitions, event batch application, out-of-order batch
  rejection.
- **E2E (Playwright):** the six demo scenarios driven end to end against a real backend —
  type code, run, step forward 20, step back 20, assert the variables panel matches the
  state at step 0; drag the slider; open the AI panel; switch a view.
- **Visual regression:** deliberately **not** pixel-diffing the whole canvas (too brittle for
  force-directed graphs). Instead, structural snapshots: node/edge counts, annotation
  positions, class names.

---

## Y.7 Performance tests

`tests/bench/` produces the numbers used in §AA, run as a benchmark job, not as a pass/fail
gate (except for regression thresholds):

- overhead ratio per granularity across the fixture corpus
- events/second and bytes/event
- reducer throughput (steps/sec), `state_at` latency at n = 1k/10k/100k
- checkpoint memory vs K
- end-to-end latency: `POST` → first WS event, and → `finished`
- frontend: time-to-first-render, step latency, view render at 1k-element arrays

Regression gate: a > 25% degradation on reducer throughput or end-to-end latency fails CI.

---

## Y.8 CI pipeline

```yaml
on: [push, pull_request]
jobs:
  backend:   ubuntu + windows × py3.11,3.12 → ruff, mypy, pytest -m "not docker", coverage
  security:  ubuntu → pytest -m docker (full adversarial suite, container limits asserted)
  frontend:  node 20 → tsc --noEmit, eslint, vitest
  invariants: → test_layering, test_plugin_isolation, test_no_algorithm_names_in_views,
               test_reducer_parity          # these four gate merge
  e2e:       → playwright against a built stack
  bench:     nightly → publish metrics, fail on >25% regression
```

Coverage targets: `core/` `state/` `languages/python/` ≥ 90%; `lifters/` `shapes/` ≥ 85%;
overall ≥ 80%. Coverage is a floor, not a goal — the invariant tests are what actually
protect the design, and they would still matter at 60% coverage.

---

## Y.9 What we are deliberately not testing

- CPython's own semantics (we test *our* preservation of them, not Python).
- LLM answer quality as a pass/fail gate — it is non-deterministic. It is *measured* in §AA
  against a fixed question set, and only the **verifier** is unit-tested.
- Force-directed layout aesthetics (structural assertions only).
- Container escape resistance beyond the documented threat model (T4 is out of scope, and a
  test that pretended otherwise would be dishonest).
