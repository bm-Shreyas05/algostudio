# AlgoStudio

**A language-agnostic, event-sourced execution model for general-purpose program
visualization, time-travel debugging, and state-grounded AI explanation.**

AlgoStudio does not visualize *algorithms*. It visualizes *executions*. A program
is reduced to a totally-ordered, strongly-typed stream of semantic events, and
every downstream capability — time travel, variable inspection, data-structure
rendering, complexity analytics, AI explanation — is a pure function of that
stream.

```
source ──► language frontend ──► instrumented AST ──► sandboxed execution
                                                              │
                                                        event stream
                                                              │
                    ┌─────────────────────────┬───────────────┴────────────┐
                    ▼                         ▼                            ▼
            state (R / R⁻¹)             analytics                grounded AI
                    │
              view resolution ──► generic renderers
```

---

## The three claims this repository exists to test

| | Claim | How it is checked |
|---|---|---|
| **INV-1** | Adding an algorithm changes **zero** core files. | Algorithms are metadata + ordinary source, discovered by a filesystem scan. No registry to edit. |
| **INV-2** | Adding a language changes nothing in `state/`, `lifters/`, `shapes/`, `analytics/`, `ai/`, `api/`, or the frontend. | Frontends implement `LanguageFrontend` and emit the shared `Event` schema. |
| **INV-3** | Any step *n* of any execution is reconstructible without re-running the program. | Event sourcing + checkpoints; invertible events give O(1) reverse stepping. |

The clearest demonstration is **Bubble Sort**. Its `source.py` contains no
annotations of any kind, yet the timeline shows `swap [0] ↔ [1]` and
`compare [0] vs [1] 5 > 2 → true`. Those were *inferred* from the generic event
stream by structural pattern matchers ("lifters") that have never heard of
bubble sort — and which fire identically on a student's own code.

---

## Quick start

Requires Python 3.11+ and Node 20+.

```bash
# backend  (http://127.0.0.1:8000, API docs at /docs)
cd backend
pip install fastapi "uvicorn[standard]"
python -m uvicorn algostudio.api.app:app --port 8000

# frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

Then open <http://localhost:5173>, pick an algorithm, and press Run.
Arrow keys step forward and backward; space plays.

The site has five pages: `/` explains what this is, `/app` is the studio,
`/faq`, `/privacy` and `/terms`. Everything except `/app` is static HTML with
no JavaScript, so those pages load instantly and are readable without a
runtime.

> **Windows note.** Execution recordings are written under `var/executions/<id>/`.
> If the repository lives at a deep path you may exceed the 260-character
> `MAX_PATH` limit — set `ALGOSTUDIO_DATA` to something short such as `C:\asdata`.

### Verify the two load-bearing claims

```bash
cd backend
python tools/check_semantics.py     # instrumented behaviour == native behaviour
python tools/check_timetravel.py    # state_at(n) and step_back are exact
```

Both run over the full fixture corpus (51 programs). The first is the more
important one: if instrumentation changes what a program does, every event,
state, view and explanation built on top is describing something the user did
not write — and the failure is invisible.

A third harness checks the *pictures* rather than the exit codes — it runs all
49 plugins, samples the view plan and live annotations through each run, and
flags any algorithm whose visualization is empty, anonymous or unmarked:

```bash
cd backend && python tools/audit_views.py     # 48/49 clean
```

### Deploy it

```bash
make build && make preflight     # build the site; refuse to ship an unsafe config
make check-site                  # meta, canonicals, headings, links, schema, 404
make up                          # API + site in one container, Docker sandbox
```

[`docs/20-deployment.md`](docs/20-deployment.md) covers both postures — the
curated public link and the full VPS deployment — and is explicit about which
one you are allowed to give a stranger.

---

## What is actually supported

Read [`docs/19-capability-matrix.md`](docs/19-capability-matrix.md) before
believing anything else. The short version:

**Full** — variables, all arithmetic and comparison, `if`/`elif`/`else`, `while`,
`for` (range, collections, `enumerate`, `zip`, generators), `break`/`continue`,
loop `else`, functions with defaults/`*args`/`**kwargs`, recursion, closures,
`global`/`nonlocal`, lists/tuples/dicts/sets/strings, subscripts and slices,
container methods, `deque`, `heapq`, `try`/`except`/`finally`, custom exceptions,
uncaught exceptions (the trace stays navigable).

**Partial** — classes, generators, comprehensions, lambdas, decorators, `with`,
`match`. These execute correctly but are traced at statement level; the UI says
so at the affected line.

**Blocked** — `async`/`await`, threading, file I/O, network, `eval`/`exec`,
non-allowlisted imports.

The system is described as *general-purpose program execution visualization*.
It is not claimed to visualize arbitrary Python, and the boundary above is the
contract.

---

## Repository layout

```
docs/          21-part design set (problem statement through deployment)
backend/
  algostudio/
    core/        event model, value encoding, IR      — stdlib only
    languages/   the ONLY language-aware layer
    runtime/     probes + recorder; runs INSIDE the sandbox
    sandbox/     process and container isolation
    state/       R, R⁻¹, checkpointed timeline
    lifters/     generic events ──► semantic events
    shapes/      structure ──► view proposals
    analytics/   event folds, growth-curve fitting
    plugins/     discovery and validation
    algorithms/  DATA ONLY — adding one touches nothing else
    ai/          grounded context, template explainer, claim verifier
    api/         REST + WebSocket
  tools/       invariant checkers, the view audit, preflight, retention sweep
  tests/       fixture corpus + the deployment-surface suite
deploy/        Caddyfile, systemd unit, retention timer
frontend/
  index.html   landing page   ┐
  faq.html     privacy.html   ├ static, zero JavaScript, CSS inlined at build
  terms.html   404.html       ┘
  app.html     the studio (the SPA entry point)
  public/      favicons, social card, web manifest — generated by scripts/
  scripts/     brand assets, and fetching the self-hosted Pyodide runtime
  src/
    engine/    TypeScript mirror of the reducer, and the Pyodide bridge
    views/     generic renderers — no algorithm ever named here
    components/IDE panels
    site.css   the static pages
render.yaml    curated public deployment (Render blueprint)
```

---

## Security

User code never runs in the API process. See
[`docs/06-sandbox.md`](docs/06-sandbox.md) for the threat model, stated
honestly: the in-process restrictions (import allowlist, builtins denylist) are
**defense in depth, not a security boundary** — CPython cannot be sandboxed
in-process. The boundary is the OS process and, in production, the container.
`ALGOSTUDIO_SANDBOX=docker` is required for any multi-user deployment.

Because that is a rule and not a suggestion, it is enforced rather than
documented: `make preflight` exits non-zero if arbitrary code is enabled
without the container sandbox, and `GET /api/v1/health` reports the same
warnings.

The public deployment sidesteps the question entirely. It runs with
`ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0` — the server refuses source it did not ship
with, and returns 403 — while **code you type runs inside your own browser**,
on a Pyodide build of the same engine. Nothing you write is uploaded, and there
is no server-side sandbox in the path to be strong enough.
[`docs/21-pyodide-spike.md`](docs/21-pyodide-spike.md) covers how that was
established (49 of 51 fixtures byte-identical to native CPython) and what it
cost.

Infinite loops are stopped by an in-process budget guard rather than an OS
timeout, so `while True:` yields the first 200,000 events of the loop as a
navigable trace instead of a hang — which is the material you need to see *why*
it never terminates.

---

## Status

Design documents and the MVP (backend + frontend) are complete and working, and
the deployment path in `docs/20-deployment.md` is implemented — both modes, with
the unsafe combination refused by `make preflight`.

Verification runs mainly through the three harnesses above rather than the full
pytest suite described in `docs/14-testing-strategy.md`. `tests/` currently holds
the fixture corpus plus `test_deployment.py`; the rest of that suite, Docker-mode
verification on a real daemon, and the V2 items (graph editor, live breakpoints,
synchronized algorithm comparison) are not built yet.

No experimental results are reported anywhere in `docs/`. The evaluation
protocols in `docs/15-research-and-evaluation.md` have empty result columns by
design — they are filled by running the studies, not by predicting them.
