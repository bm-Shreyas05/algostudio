# 03 — State Model & Time-Travel Debugging

*(Deliverables I, and §5–§6 of the brief)*

---

## I.1 The state model

```python
ExecutionState:
    step:        int                       # index of the last applied event
    status:      running|finished|error|budget_exceeded
    frames:      list[Frame]               # call stack, index 0 = module frame
    heap:        dict[Ref, HeapObject]     # every container/object ever referenced
    globals:     dict[str, EncodedValue]   # module-level bindings (mirror of frames[0])
    stdout:      str                       # accumulated program output
    stderr:      str
    current_loc: Loc | None                # source line the program is "at"
    loops:       dict[LoopId, LoopState]   # active + finished loop bookkeeping
    exception:   ExceptionInfo | None
    annotations: dict[str, Annotation]     # from ALGORITHM_EVENTs: marks, pointers, regions
    counters:    dict[str, int]            # live analytics fold

Frame:
    frame_id:    int
    func_name:   str
    qualname:    str
    depth:       int
    call_loc:    Loc | None                # where the caller called from
    locals:      dict[str, EncodedValue]   # ordered by first binding
    args:        list[str]
    return_value: EncodedValue | None
    active:      bool

LoopState:
    loop_id: str; kind: for|while; iteration: int; started_step: int; finished: bool

Annotation:                                # e.g. {"kind":"pointer","target":"h7","index":3,"label":"mid"}
    kind: pointer|mark|region|highlight|note
    target_ref: Ref | None
    index / range / label / color / ttl_steps
```

### Why an explicit heap

Because aliasing is a first-class teaching concept and a first-class bug source.

```python
a = [1, 2, 3]
b = a
b.append(4)      # a is now [1,2,3,4] — the single most common beginner surprise
```

A flat `name -> value` model shows two independent lists and *teaches the wrong thing*. A
`name -> ref` + `ref -> object` model shows one object with two arrows, which is the truth.
Every container-typed value in `frames[*].locals` is a `{"k":"ref","r":"hN"}`, and the
renderer draws the arrow.

### Why `annotations` are in state, not just in events

Views need to know "where is the `mid` pointer *right now*", not "was there ever a pointer
event". Annotations are applied by the reducer with an optional `ttl_steps` so a transient
`compare` highlight decays after N steps instead of accumulating. This keeps the view a
function of state alone — the renderer never scans backwards through events.

---

## I.2 The reducer

```python
def apply(state: ExecutionState, ev: Event) -> ExecutionState        # R
def unapply(state: ExecutionState, ev: Event) -> ExecutionState      # R'
```

Implemented as two dispatch tables `EventType -> handler`. Properties, all property-tested:

- **Totality of `R`**: an unknown event type is a no-op that bumps `step`. This is what
  makes forward compatibility real rather than aspirational.
- **Exactness of `R'`**: for every mutating type, `unapply(apply(s, e), e) == s`.
  Non-mutating events (`*_READ`, `EXPRESSION_EVALUATED`, `LINE_EXECUTED`) have a trivial
  inverse that only decrements `step` and restores `current_loc` (the previous location is
  carried in `meta.prev_loc` so the inverse remains local).
- **Determinism**: `R` never consults a clock, RNG, or the filesystem.

The only field whose inverse needs care is `stdout` (append -> truncate by recorded
length) and `counters` (increment -> decrement). Both carry their delta in the event.

---

## I.3 Time travel: the four candidate designs

| # | Approach | Seek to step n | Step back | Memory | Determinism required |
|---|---|---|---|---|---|
| **A** | Re-execute from start with a step limit | O(n) *execution* | O(n) execution | O(1) | **yes** — a program reading time/RNG/network gives a different trace |
| **B** | Snapshot full state after every step | O(1) | O(1) | O(n·\|state\|) — a 5k-step run over a 1k-element array is ~GBs | no |
| **C** | Event sourcing, forward replay only | O(n) *reduction* | O(n) reduction | O(\|events\|) | no |
| **D** | Event sourcing + **invertible events** + **periodic checkpoints** | O(K) reduction | **O(1)** | O(\|events\| + n/K·\|state\|) | no |

### Decision: **D**.

Rationale, in the order the constraints bind:

1. **A is disqualified on correctness, not performance.** Re-execution requires the program
   to be deterministic. Student code calls `random.shuffle`, `time.time`, `input()`. We
   *could* seed and record inputs to force determinism (record/replay), but that is a much
   larger engineering surface than storing events, and it fails the moment an unsupported
   nondeterminism source appears. Events are a recording of what *did* happen; there is no
   determinism assumption at all. This also means step-back works on a run that already
   crashed, which is precisely when a student needs it.

2. **B is disqualified on memory.** Concretely: merge sort on 200 elements produces ~11k
   events; the state includes a 200-element array plus recursion frames — roughly 8 KB
   encoded. 11k × 8 KB ≈ 88 MB for one execution. Multiply by concurrent users. No.

3. **C is the honest baseline** and is what most event-sourced systems stop at. Seeking to
   step 9,000 costs 9,000 reductions (~10–30 ms in Python — tolerable), but *scrubbing* the
   timeline slider issues a seek per frame, and 30 ms/frame is a visibly unusable UI.

4. **D fixes both axes with two independent mechanisms:**
   - **Invertible events** make the common case — pressing "step back" — O(1). This is the
     interaction that matters most for learning (D3 in the motivation), so it gets the
     best complexity.
   - **Checkpoints every K steps** make random seek O(K) regardless of n. With K = 64,
     the worst-case seek is 64 reductions (~0.2 ms), so slider scrubbing is smooth.

### Checkpoint sizing

Memory cost is `(n/K) × |state|`. With K = 64 and the merge-sort example: 11k/64 ≈ 172
checkpoints × 8 KB ≈ 1.4 MB. Acceptable. K is adaptive:

```
K = clamp(64, 16, 512)  scaled so that  (n/K) * estimated_state_bytes <= 32 MB
```

Checkpoints are computed lazily on the first seek into a region and cached, so a user who
only steps forward never pays for them. They are also written to
`var/executions/<id>/checkpoints/` so a reloaded session does not recompute.

### Why not deltas-only without checkpoints?

Because `OBJECT_MUTATED` (C-level mutation like `list.sort()`) carries a whole-container
before/after. Long chains of those make backward reduction expensive precisely where
checkpoints are cheap. Checkpoints bound the worst case; inverse events optimize the
common case. Using both is not redundancy, it is covering two different distributions.

### The honest limitation

`R'` is exact only if every mutation was observed. Mutation performed by code we did not
instrument — a C extension holding a reference, a `__del__` side effect, a mutating method
we did not include in the known-mutators list — is invisible. Mitigation:

1. The known-mutators list covers the container methods reachable from the supported
   subset (see `19-capability-matrix.md`).
2. Any call to an *unknown* method on a *tracked container* emits `OBJECT_MUTATED` with a
   before/after snapshot, so unknown mutations are still captured (at snapshot cost) rather
   than missed.
3. `SNAPSHOT` verification mode (dev/CI) has the child emit full state every 250 steps and
   asserts the reducer agrees. Divergence fails the test suite. This is how we know the
   claim in INV-3 is true rather than believed.

---

## I.4 The timeline API

```python
class Timeline:
    def __init__(self, events: Sequence[Event], checkpoint_interval: int = 64)
    def state_at(self, step: int) -> ExecutionState      # checkpoint + forward replay
    def step_forward(self, s: ExecutionState) -> ExecutionState
    def step_back(self, s: ExecutionState) -> ExecutionState     # O(1) via unapply
    def seek(self, s: ExecutionState, target: int) -> ExecutionState
        # chooses the cheaper of: unapply backwards | replay from nearest checkpoint
    def next_matching(self, s, predicate) -> int | None           # step-over / breakpoints
```

`seek` picks a strategy by cost model:

```
backward_cost = current_step - target                      (inverse reductions)
forward_cost  = target - nearest_checkpoint_at_or_before(target)
strategy = backward if backward_cost <= forward_cost else checkpoint_replay
```

This single rule gives correct behaviour for: step back (cost 1), scrub left a long way
(checkpoint), scrub right (checkpoint or forward replay), and jump to the last event.

---

## I.5 Transport controls (§5 of the brief)

| Control | Implementation |
|---|---|
| Step forward / back | `Timeline.step_forward/back` on the client mirror; no server round-trip |
| Play / pause / speed | client-side interval driving `step_forward`; events already local |
| Restart | `seek(0)` — the program is **not** re-run |
| Jump to step | `seek(n)` |
| Replay | `seek(0)` then play |
| Step over line | `next_matching(LINE_EXECUTED and depth <= current)` |
| Step into | `next_matching(FUNCTION_ENTERED)` |
| Step out | `next_matching(FUNCTION_EXITED and frame == current)` |
| Run to breakpoint | `next_matching(line in breakpoints and (cond evaluates true))` |

**The key consequence:** because the entire execution is already recorded and the client
holds a mirror of the reducer, *all* debugger navigation is local, instantaneous, and
works in both directions. There is no debug protocol, no stopped/running state machine, no
risk of the child hanging. This is the "sensible educational approximation" §21 asks for —
and for education it is arguably *better* than real debugger semantics, because you can
step backwards out of a function you already returned from.

The trade-off, stated plainly: breakpoints do not stop a *live* process, so you cannot
modify state mid-run and continue. Interactive control of the live child is V2 and requires
a bidirectional control channel into the sandbox (`04`/`W`).

---

## I.6 Client/server state division

The client holds `[Event]` (streamed) and runs the **same reducer logic** in TypeScript.
Two implementations of `R` is a duplication risk, so:

- The TS reducer is generated-adjacent: both are driven by the same event-type table, and
  `tests/test_reducer_parity.py` runs fixture executions through the Python reducer and
  compares the JSON state against the TS reducer executed under Node. Divergence fails CI.
- For executions larger than `MAX_CLIENT_EVENTS` (default 50k), the client falls back to
  server-side `GET /state?step=n`, trading latency for memory. The UI is identical.
