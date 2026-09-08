# 02 — Event Model

*(Deliverable H)*

The event model is the contract that makes every other invariant possible. Get it wrong
and either the reducer cannot be inverted (no time travel), or the renderer needs
algorithm knowledge (no generality), or the AI has nothing to be grounded in.

---

## H.1 Design constraints

| # | Constraint | Consequence for the schema |
|---|---|---|
| C1 | Every mutating event must be **invertible** | it carries `old` *and* `new` |
| C2 | Events must be **totally ordered** | monotonic `logical_step`, assigned in the child |
| C3 | Events must be **self-describing** for a renderer that knows no algorithms | payloads carry structural typing (`kind`, `container_ref`, `index`) |
| C4 | Events must be **cheap** | flat payloads, ints not strings where possible, no nesting beyond depth 3 |
| C5 | Events must be **extensible without breaking old readers** | closed enum for core types + open `ALGORITHM_EVENT` with a `name` field |
| C6 | Events must **not leak object identity across runs** | heap refs are per-execution synthetic ids (`h17`), never `id()` |
| C7 | Values must be **bounded** | encoding truncates by depth/length/bytes and marks truncation explicitly |

C1 and C5 are the two decisions that do the most work. C1 is what buys O(1) reverse
stepping. C5 is what lets a plugin, a lifter, or a future language emit semantics the core
has never heard of without a schema migration.

---

## H.2 Envelope

Every event, regardless of type, is:

```jsonc
{
  "id": 1423,                  // event_id: dense index within this execution
  "step": 1423,                // logical_step: monotonic; multiple events may share a step
  "t": 0.014217,               // seconds since program start (monotonic clock, child-side)
  "type": "SUBSCRIPT_WRITTEN", // EventType
  "frame": 3,                  // execution frame id (0 = module frame)
  "depth": 2,                  // call depth, denormalized for cheap timeline rendering
  "loc": { "line": 17, "col": 8, "end_line": 17, "end_col": 22 },
  "payload": { ... },          // type-specific, see below
  "meta": { ... }              // optional: origin, lifter id, granularity, confidence
}
```

Notes on the envelope:

- `step` vs `id`: `id` is the array index. `step` is the *logical* clock. They coincide
  for recorded events; **lifted** events are inserted with the `step` of the last raw event
  they consumed and receive fresh `id`s on renumbering. This lets the timeline collapse a
  lifted `SWAP` and the three raw writes that produced it into one row.
- `frame` is a synthetic monotonically increasing frame id, not a stack index — this makes
  recursion unambiguous (`fib` frames 4, 7, 9 are distinct) and lets the call-tree view be
  reconstructed exactly.
- `loc` refers to **original source**, never instrumented source. The transformer preserves
  locations via `ast.copy_location`; the `SourceMap` is an identity map for Python and a
  real map for future frontends.
- `meta.origin` is one of `runtime` (recorded by a probe), `lifted` (synthesized by a
  lifter), `semantic` (explicit `algo.*` call in user code), `harness` (sandbox-level).

---

## H.3 Event taxonomy

### Tier 0 — Lifecycle

| Type | Payload | Invertible |
|---|---|---|
| `PROGRAM_STARTED` | `{language, granularity, source_hash, argv, entry}` | n/a |
| `PROGRAM_FINISHED` | `{status: ok\|error\|budget_exceeded\|killed, duration_ms}` | n/a |
| `STDOUT_WRITE` | `{text}` | append -> truncate |
| `STDERR_WRITE` | `{text}` | append -> truncate |
| `STDIN_READ` | `{prompt, text}` | — |

### Tier 1 — Control flow

| Type | Payload |
|---|---|
| `LINE_EXECUTED` | `{}` (line is in `loc`) |
| `CONDITION_EVALUATED` | `{kind: if\|while\|ifexp\|comprehension, result: bool, expr: str, operands: [EncodedValue]}` |
| `BRANCH_TAKEN` | `{branch: then\|else\|none, cond_event_id}` |
| `LOOP_STARTED` | `{loop_id, kind: for\|while, iterable_ref?}` |
| `LOOP_ITERATION` | `{loop_id, iteration, var?, value?}` |
| `LOOP_FINISHED` | `{loop_id, iterations, exit: normal\|break\|return\|exception}` |
| `FUNCTION_ENTERED` | `{func_id, name, qualname, args: {name: EncodedValue}, caller_frame}` |
| `FUNCTION_RETURNED` | `{func_id, value: EncodedValue}` |
| `FUNCTION_EXITED` | `{func_id, reason: return\|fallthrough\|exception}` |
| `EXCEPTION_RAISED` | `{exc_type, message, traceback_lines}` |
| `EXCEPTION_HANDLED` | `{exc_type, handler_line}` |

`FUNCTION_RETURNED` and `FUNCTION_EXITED` are separate because a function can exit without
returning (exception, fallthrough). The call-tree view needs both to draw an accurate
recursion tree with failed branches.

### Tier 2 — Data (the invertible core)

Every event in this tier carries the information needed by `R'`.

| Type | Payload | Inverse |
|---|---|---|
| `VARIABLE_CREATED` | `{name, scope: local\|global\|nonlocal\|arg, value}` | delete binding |
| `VARIABLE_WRITTEN` | `{name, scope, old, new}` | set binding to `old` |
| `VARIABLE_READ` | `{name, scope, value}` | no-op (still recorded, for provenance + analytics) |
| `VARIABLE_DELETED` | `{name, scope, old}` | restore binding to `old` |
| `SUBSCRIPT_READ` | `{container_ref, index, value}` | no-op |
| `SUBSCRIPT_WRITTEN` | `{container_ref, index, old, new, existed: bool}` | restore index to `old` (or delete if `!existed`) |
| `SUBSCRIPT_DELETED` | `{container_ref, index, old, position}` | reinsert `old` at `position` |
| `ATTRIBUTE_READ` | `{object_ref, name, value}` | no-op |
| `ATTRIBUTE_WRITTEN` | `{object_ref, name, old, new, existed}` | restore |
| `OBJECT_CREATED` | `{ref, kind, snapshot: EncodedValue, ctor?}` | remove from heap |
| `OBJECT_MUTATED` | `{ref, op, args, before: EncodedValue, after: EncodedValue}` | restore `before` |
| `OBJECT_FREED` | `{ref, snapshot}` | reinsert |
| `EXPRESSION_EVALUATED` | `{expr, op?, operands: [EncodedValue], value}` | no-op |

`OBJECT_MUTATED` is the escape hatch for C-level mutation (`list.sort()`, `dict.update()`,
`heapq.heappush`) that per-element probes cannot observe. The probe snapshots the receiver
before and after the call and records both. This is the only place where the inverse
carries a full container copy, and it is why `OBJECT_MUTATED` is emitted *only* for calls
to known-mutating methods rather than for every method call — a cost/fidelity trade
documented in `03`.

### Tier 3 — Structural collections (derived, redundant-by-design)

These are convenience events emitted alongside Tier 2 so the renderer does not have to
infer structure. They are **not** independently invertible; they are projections.

| Type | Payload |
|---|---|
| `COLLECTION_CREATED` | `{ref, kind: list\|dict\|set\|tuple\|deque, length}` |
| `COLLECTION_RESIZED` | `{ref, old_length, new_length}` |
| `STACK_PUSH` / `STACK_POP` | `{ref, value, depth}` |
| `QUEUE_ENQUEUE` / `QUEUE_DEQUEUE` | `{ref, value, length}` |

`STACK_PUSH` is emitted when `list.append` is called on a container that a shape detector
currently classifies as stack-like, or when the user calls `algo.push(...)`. It is
**advisory**: the authoritative mutation is the `OBJECT_MUTATED` event next to it.

### Tier 4 — Algorithm-level (open set)

| Type | Payload |
|---|---|
| `ALGORITHM_EVENT` | `{name: str, args: {..}, category?: str, ref?: str}` |

Reserved `name` values with defined semantics for the built-in views:

`compare` · `swap` · `visit` · `discover` · `relax` · `enqueue` · `dequeue` ·
`partition` · `merge` · `pivot` · `mark` · `unmark` · `highlight` · `annotate` ·
`region` · `pointer` · `metric`

Anything else is carried through and rendered generically (as a timeline row plus a
key/value annotation) — an unknown `name` must never be an error. That is C5.

`ALGORITHM_EVENT`s are produced by two independent mechanisms:

1. **Explicit** — user or plugin code calls `algo.swap(arr, i, j)`.
2. **Lifted** — a lifter recognizes the pattern in generic events.

Both produce identical envelopes distinguished only by `meta.origin`, so the UI, analytics
and AI treat them uniformly. A student who writes a swap the "normal" way gets the same
`SWAP` visualization as a plugin author who annotated it.

### Tier 5 — Harness

`BUDGET_WARNING`, `BUDGET_EXCEEDED`, `INSTRUMENTATION_SKIPPED` (a construct the
transformer declined to instrument, with the reason — this is how the capability boundary
becomes visible in the UI instead of silently producing a wrong picture),
`SNAPSHOT` (full state resync, dev/verification only).

---

## H.4 Value encoding (`EncodedValue`)

Values crossing the sandbox boundary are encoded into a bounded, JSON-safe form:

```jsonc
// primitives — inline
{"k":"int","v":42}
{"k":"float","v":3.5}
{"k":"str","v":"hello","len":5}
{"k":"bool","v":true}
{"k":"none"}
// containers — by reference into the heap
{"k":"ref","r":"h7","t":"list","n":8}          // t=type tag, n=length (for cheap previews)
// truncation is explicit, never silent
{"k":"str","v":"aaaa…","len":100000,"trunc":true}
{"k":"ref","r":"h9","t":"list","n":50000,"trunc":true}
// unrepresentable
{"k":"opaque","t":"socket","repr":"<socket ...>"}
{"k":"cycle","r":"h3"}
```

Heap objects:

```jsonc
{"ref":"h7","t":"list","n":3,"items":[{"k":"int","v":1},{"k":"int","v":2},{"k":"ref","r":"h8","t":"list","n":2}]}
{"ref":"h8","t":"dict","n":2,"entries":[[{"k":"str","v":"a"},{"k":"int","v":1}], ...]}
{"ref":"h9","t":"object","cls":"Node","fields":{"val":{"k":"int","v":5},"left":{"k":"ref","r":"h10","t":"object"}}}
```

**Ref allocation.** The recorder keeps `id(obj) -> ref` in a dict plus a strong reference
in a keep-alive list. Strong references prevent `id()` reuse after GC (which would corrupt
the heap model) at the cost of preventing collection during the run — acceptable because
the run is budget-bounded, and it is the same trade-off Python Tutor makes. `OBJECT_FREED`
is therefore only emitted for explicit `del` of the last binding, not for GC.

**Encoding budget.** `max_depth=6`, `max_items=256`, `max_str=512`, `max_bytes_per_event=64KiB`.
Exceeded limits set `trunc:true`. A truncated value degrades the *view*, never the
*correctness of the reducer*, because the reducer works on refs and indices.

---

## H.5 Granularity policy

Event volume is the dominant cost, and granularity is a first-class, measurable knob
(this is research question RQ5).

| Level | Emits | Typical events for `binary_search(1000 elems)` |
|---|---|---|
| `minimal` | lifecycle, lines, variable writes, function enter/exit/return, algorithm events | ~120 |
| `standard` *(default)* | + conditions, branches, loops, subscript read/write, object mutation | ~380 |
| `verbose` | + every name read, every binary/compare sub-expression, attribute access | ~1,600 |

Granularity is applied at **instrumentation time** (probes are not emitted at all), not at
filter time, so the cost is genuinely avoided rather than hidden.

---

## H.6 Worked example

```python
1  x = 5
2  for i in range(3):
3      x += i
```

`standard` granularity, abridged (`t` omitted):

```
id  step type                 loc  payload
0   0    PROGRAM_STARTED      -    {language:python, granularity:standard}
1   1    LINE_EXECUTED        1    {}
2   2    VARIABLE_CREATED     1    {name:x, scope:global, value:{k:int,v:5}}
3   3    LINE_EXECUTED        2    {}
4   4    LOOP_STARTED         2    {loop_id:L1, kind:for}
5   5    LOOP_ITERATION       2    {loop_id:L1, iteration:0, var:i, value:{k:int,v:0}}
6   6    VARIABLE_CREATED     2    {name:i, scope:global, value:{k:int,v:0}}
7   7    LINE_EXECUTED        3    {}
8   8    VARIABLE_READ        3    {name:x, value:{k:int,v:5}}
9   9    EXPRESSION_EVALUATED 3    {op:'+', operands:[{k:int,v:5},{k:int,v:0}], value:{k:int,v:5}}
10  10   VARIABLE_WRITTEN     3    {name:x, scope:global, old:{k:int,v:5}, new:{k:int,v:5}}
11  11   LOOP_ITERATION       2    {loop_id:L1, iteration:1, var:i, value:{k:int,v:1}}
12  12   VARIABLE_WRITTEN     2    {name:i, scope:global, old:{k:int,v:0}, new:{k:int,v:1}}
...
22  22   LOOP_FINISHED        2    {loop_id:L1, iterations:3, exit:normal}
23  23   PROGRAM_FINISHED     -    {status:ok, duration_ms:2}
```

From this stream alone, with no knowledge that this is a loop accumulating a sum, the
system can render: the source with line 3 highlighted, `x: 5 -> 5 -> 6 -> 8`, a loop badge
showing iteration 2 of 3, a timeline with collapsible per-iteration groups, and analytics
reporting 3 iterations / 3 variable writes / 0 comparisons. That is the property the whole
architecture exists to produce.

---

## H.7 Schema evolution

The event schema carries `schema_version` in `PROGRAM_STARTED`. Rules:

1. New event types may be added at any time; readers must ignore unknown `type` values
   (they render as a generic timeline row).
2. Payload fields may be **added**; never renamed or removed within a major version.
3. `ALGORITHM_EVENT.name` is an open string set by design — new semantics need **no**
   schema change, which is why plugins and lifters can be developed independently of core.

A stored execution from schema v1 must remain replayable by a v1.x reader; this is tested
by keeping golden event logs in `tests/golden/` and replaying them in CI.
