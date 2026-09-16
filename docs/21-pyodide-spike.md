# 21 — Pyodide spike: can the engine run in the browser?

*(A time-boxed investigation, not a design document. It exists because the
public deployment cannot execute visitor code — the free tier has no container
sandbox — and `docs/13-roadmap-and-scope.md` §X already names client-side
execution as the V3 answer. The question was whether that answer is real.)*

---

## A. The question

> Can Pyodide instrument and run a program and emit the **same event stream**
> as the server?

Not "can it run Python" — obviously it can. The event stream is the contract
every downstream capability depends on, so a browser that produced a *slightly*
different stream would be worse than one that failed outright: every claim about
time travel, view resolution and grounded explanation is a claim about that
stream being a faithful record.

## B. Method

`tools/make_pyodide_fixtures.py` runs all 51 fixtures through the **unmodified**
sandbox child entrypoint and records a SHA-256 of each normalised event stream.
A browser harness unpacks the same engine into Pyodide, runs the same fixtures,
hashes with the same Python code — not a JavaScript re-implementation — and
compares.

Three fields are excluded, and only three: `t` and `duration_ms` are clock
readings, and `python` is the interpreter version. Everything else — event
order, ids, frames, depths, payloads — must match exactly.

## C. Result: **yes, with one documented caveat**

| | |
|---|---|
| Fixtures byte-identical to native CPython | **49 / 51** |
| Engine changes needed to run in Pyodide | **none** |
| Engine payload | 47 KB (20 modules: `core`, `languages`, `runtime`) |
| Pyodide cold load | ~2.6 s |
| Whole 51-fixture corpus, executed in-browser | **1.7 s** |

`child_main.py` ran **unchanged**. It reads a job directory and writes
`events.jsonl` and `result.json`, and Pyodide's virtual filesystem satisfies
that without modification. The runtime path turned out to import nothing
Pyodide lacks — `threading`, `signal`, `subprocess` and `socket` appear in the
codebase only as *denylist strings*.

## D. The caveat: set iteration order

The two fixtures that differ are `algorithms/bfs.py` and `algorithms/dijkstra.py`.
Both iterate a `set` of strings, and their event counts and statuses match
exactly — only the order differs.

| | Server (x86-64) | Browser (wasm32) |
|---|---|---|
| `sys.hash_info.width` | 64 | **32** |
| `sys.hash_info.algorithm` | siphash13 | **fnv** |
| `list({"A".."G"})` | `B F G D A E C` | `A C B E D G F` |

`PYTHONHASHSEED=0` — which `sandbox/limits.py` already pins — is necessary but
not sufficient: Pyodide is a 32-bit build using a different hash function, so
string hashing differs and set order with it.

**This is not a defect in either.** Python does not define set iteration order,
and the same divergence appears between any two CPython builds of different word
size. Both traces are correct executions of the program. But it is a real design
constraint:

> A program whose behaviour depends on set iteration order will produce a
> different — still correct — trace in the browser than on the server. An
> execution must therefore be attributed to where it ran, and a cached
> server-side recording must not be silently served in place of a browser run of
> the same source.

## E. What the spike found in the existing engine

Worth more than the spike's own answer.

**Three consecutive native runs of the same program produced three different
event streams.** `enc_opaque` passed `repr()` straight through, and `repr()` of
a function embeds its address — `<function f at 0x7f3c8a1b2d40>`. The module
docstring in `core/values.py` had always documented the intended form as
`<function f>`; the implementation simply did not do it.

It survived because nothing looked wrong: the address is cosmetic. But it
quietly falsified things the architecture leans on — that a cached recording is
interchangeable with a fresh one (`db.find_cached` serves one for the other),
that the differential harness compares like with like, and that a recording can
be hashed or compared at all.

Fixed in `core/values.py`; covered by `tests/test_reproducibility.py`, which was
validated by reintroducing the bug (8 failures) and reverting it (0).

## F. Verdict

Green light. The expensive unknown — *does the engine produce the same events in
a browser* — is answered, and the answer is yes for 49 of 51 fixtures with the
two exceptions understood and explainable.

**What remains is plumbing, and it is not small.** The execution path ports
unchanged, and `frontend/src/engine/` already mirrors the reducer in TypeScript.
But `lifters/`, `shapes/` and `analytics/` are server-side Python and would have
to run in Pyodide too — they are pure Python, so this is packaging and wiring
rather than research. The remaining work is:

1. ship `lifters/`, `shapes/`, `analytics/` in the browser bundle (they add to
   the 47 KB, all pure Python);
2. a JS bridge that returns events, view plans and analytics to the existing UI
   in place of the HTTP calls;
3. a mode switch so `/app` uses the browser engine for visitor code and the
   server for the bundled catalogue;
4. progress and download UI for the ~10 MB Pyodide fetch, cached thereafter.

None of it is speculative. All of it is work.
