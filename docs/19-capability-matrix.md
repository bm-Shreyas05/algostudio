# 19 — Capability Matrix

*(§45, §46 of the brief)*

This is the **contract**. Anything claimed elsewhere in the documentation is bounded by this
table. The project's public description is *"general-purpose program execution
visualization"* — never *"visualizes any code"*.

---

## Levels

| Level | Meaning | What the user sees |
|---|---|---|
| **FULL** | Executes correctly **and** produces fine-grained semantic events | complete visualization |
| **PARTIAL** | Executes correctly; instrumented at statement level only | correct but coarser view; the line is marked in the capability banner |
| **DEGRADED** | Executes correctly; state observed by frame diff after the statement | values correct, sub-statement detail absent; banner shows the line |
| **BLOCKED** | Refused before execution with a precise message | 422 with line/col, or a runtime denial event |

Every row is backed by at least one fixture in `backend/tests/fixtures/`. A row without a
fixture fails the meta-test — that is how this table stays true rather than aspirational.

---

## Language constructs

| Construct | Level | Notes |
|---|---|---|
| Integer / float / bool / None / str literals | FULL | |
| Variable assignment (`x = e`) | FULL | old/new captured, scope classified |
| Multiple assignment (`a = b = e`) | FULL | one event per target |
| Tuple/list unpacking (`a, b = e`) | FULL | via post-statement sync; exact values |
| Starred unpacking (`a, *rest = e`) | DEGRADED | values correct, no per-element detail |
| Nested unpacking (`(a,(b,c)) = e`) | DEGRADED | |
| Augmented assignment (`x += e`) | FULL | single evaluation of the target preserved |
| `del x`, `del a[i]`, `del d[k]` | FULL | invertible |
| Chained comparison (`a < b < c`) | PARTIAL | whole-chain result only; short-circuit preserved |
| Boolean ops (`and`, `or`, `not`) | PARTIAL | result captured; short-circuit preserved |
| Conditional expression (`a if c else b`) | PARTIAL | condition result captured |
| Walrus (`:=`) in statements | PARTIAL | |
| Walrus inside a comprehension | DEGRADED | comprehension scope; see below |
| `if` / `elif` / `else` | FULL | condition value + branch taken |
| `while` (+ `else`) | FULL | per-iteration events, correct exit reason |
| `for` over range/list/tuple/str/dict/set | FULL | loop var write per iteration |
| `for` over `enumerate`/`zip`/`reversed`/`sorted` | FULL | |
| `for` over a generator / custom iterator | FULL | laziness preserved (wrapper is a generator) |
| `for`/`while` … `else` | FULL | |
| `break` / `continue` | FULL | correct `LOOP_FINISHED.exit` |
| Nested loops (any depth) | FULL | `loop_id` disambiguates |
| Function definition & call | FULL | args captured by name |
| Default / keyword / `*args` / `**kwargs` | FULL | |
| Keyword-only & positional-only params | FULL | |
| Recursion (incl. mutual) | FULL | capped at `max_recursion` (default 200) |
| `return` (incl. bare, incl. multiple) | FULL | |
| Closures, `nonlocal`, `global` | FULL | scope classified correctly |
| Lambda | PARTIAL | called, result captured; body not instrumented |
| Decorators | PARTIAL | decorator runs; the decorated body is instrumented |
| Generators (`yield`) | PARTIAL | function entry/exit and yields at statement level |
| List / dict / set comprehensions | PARTIAL | statement-level; result value captured. *Reason: comprehensions have their own scope in Python 3; naive probe insertion changes name resolution* |
| Generator expressions | PARTIAL | |
| Classes: definition, `__init__`, methods, attributes | PARTIAL | objects on the heap with fields; method calls traced; single inheritance |
| Multiple inheritance / MRO subtleties | DEGRADED | executes; not modelled |
| `@property`, descriptors, `__slots__` | DEGRADED | executes; attribute events may be missing |
| Dunder operator overloads (`__add__`, `__lt__`, …) | PARTIAL | called correctly; body instrumented if user-defined |
| `try` / `except` / `else` / `finally` | FULL | raise, handle, and finally-path events |
| `raise`, `raise from` | FULL | |
| Custom exception classes | FULL | |
| Uncaught exception | FULL | trace remains fully navigable — this is a supported outcome, not an error |
| `assert` | FULL | |
| `with` statement | PARTIAL | body traced; `__enter__`/`__exit__` not |
| `match` / `case` | PARTIAL | statement-level |
| `async def`, `await`, `async for/with` | BLOCKED | no event model for coroutine scheduling |
| `yield from` | PARTIAL | |
| `import` (allowlisted modules) | FULL | |
| `import` (anything else) | BLOCKED | denial event names the module |
| `eval` / `exec` / `compile` | BLOCKED | removed from builtins |
| `open` / file I/O | BLOCKED | removed from builtins |
| Network (`socket`, `urllib`, `requests`) | BLOCKED | import denied; no network in container mode |
| `threading`, `multiprocessing`, `concurrent` | BLOCKED | single-threaded event model |
| `os`, `sys`, `subprocess`, `ctypes`, `inspect` | BLOCKED | |
| `input()` | FULL | fed from the request's `stdin`; emits `STDIN_READ` |
| `print()` | FULL | emits `STDOUT_WRITE`, time-scrubbed in the console |
| f-strings / `.format` / `%` | FULL | |
| Type annotations | FULL | ignored at runtime, preserved |
| `nonlocal`/`global` at module level | FULL | |

---

## Data types & structures

| Type | Level | View |
|---|---|---|
| `int`, `float`, `bool`, `None`, `complex` | FULL | inline |
| `str` | FULL | inline, truncated at 512 chars |
| `bytes`, `bytearray` | PARTIAL | inline repr, truncated |
| `list` (incl. nested) | FULL | `ArrayView` / `MatrixView` / `StackView` / `QueueView` / `HeapView` |
| `tuple` | FULL | `ArrayView` |
| `dict` (incl. nested) | FULL | `TableView` / `GraphView` |
| `set`, `frozenset` | FULL | `SetView` |
| `collections.deque` | FULL | `QueueView` |
| `collections.defaultdict`, `Counter`, `OrderedDict` | FULL | `TableView` |
| `heapq` over a list | FULL | `HeapView` (array + tree, index-linked) |
| `array.array` | PARTIAL | `ArrayView` |
| User-defined objects | PARTIAL | `ObjectView`; linked structures → `LinkedListView` / `TreeView` |
| Recursive / cyclic structures | FULL | cycle-safe encoding, `{"k":"cycle"}` |
| Slices (`a[1:5]`, `a[::-1]`) | FULL | read events; slice assignment is `OBJECT_MUTATED` |
| Very large collections (> 256 elements) | PARTIAL | truncated with `trunc:true`; view shows a window |
| Functions / classes as values | PARTIAL | `opaque` with a readable repr |
| Modules, files, sockets | PARTIAL | `opaque` |

### Mutating methods observed via `_as_method`

`list`: `append extend insert remove pop clear sort reverse` ·
`dict`: `update pop popitem setdefault clear` ·
`set`: `add discard remove pop update clear` ·
`deque`: `append appendleft pop popleft extend extendleft rotate clear` ·
`heapq`: `heappush heappop heapify heappushpop heapreplace` ·
`bytearray`: `append extend`

Any **other** method call on a tracked container also emits `OBJECT_MUTATED` with a
before/after snapshot, so unknown mutations are captured (at snapshot cost) rather than
missed. This is why the model does not silently lose state.

---

## Platform features

| Feature | Level | Notes |
|---|---|---|
| Step forward / backward | FULL | O(1) backward via inverse events |
| Jump to any step / slider scrub | FULL | checkpoint + replay, ≤ K reductions |
| Play / pause / speed | FULL | client-side |
| Restart / replay | FULL | no re-execution |
| Step over / into / out | FULL | predicate search over the recording |
| Line breakpoints | FULL | **replay-side**: run-to-step, not a live process stop |
| Conditional breakpoints | BLOCKED (V2) | needs a safe expression evaluator over state |
| Modify a variable and continue | BLOCKED | replay model; would require live control |
| Live pause/resume of a running program | BLOCKED (V2) | needs a control channel into the sandbox |
| Multi-file programs | BLOCKED (V2) | single module |
| Automatic view selection | FULL | confidence-scored, user-overridable |
| Semantic events from annotated code | FULL | `algo.*` |
| Semantic events lifted from plain code | PARTIAL | swap/compare/pointer/push-pop/relax/region; precision reported in evaluation |
| Analytics | FULL | derived from generic events |
| Complexity curve fitting | PARTIAL | fits measured ops to candidate growth models; advisory |
| Algorithm comparison | PARTIAL | metrics table; synchronized replay is V2 |
| Grounded AI explanation | FULL | with claim verification |
| Offline explanation (no LLM) | FULL | `TemplateExplainer` |
| Session save / share | FULL | |
| Python 3.11 / 3.12 | FULL | tested in CI |
| Python 3.13 | PARTIAL | PEP 667 `f_locals` semantics; untested at time of writing |
| C++ / Java / JavaScript | BLOCKED (V3) | interface exists; no implementation |

---

## Execution limits (defaults)

| Limit | Default | Behaviour on breach |
|---|---|---|
| Events | 200,000 | `BUDGET_EXCEEDED`; **partial trace is kept and is navigable** |
| Wall clock | 10 s | same |
| CPU time | 5 s | same (POSIX / container) |
| Memory | 256 MB | `MemoryError` or container OOM-kill; status recorded |
| Recursion depth | 200 | `RecursionError`, trace kept |
| Output | 1 MiB | truncated, `STDOUT_WRITE` marked `trunc` |
| Heap objects tracked | 50,000 | further objects encoded as `opaque` |
| Source size | 256 KiB | 413 before execution |
| Value depth / items / string | 6 / 256 / 512 | `trunc:true` on the encoded value |

---

## How degradation is surfaced

Never silently. Three visible mechanisms:

1. **Pre-execution** — `capability_report` in the `POST /executions` response, rendered as a
   banner and as gutter markers on the affected lines.
2. **During execution** — `INSTRUMENTATION_SKIPPED` events appear in the timeline at the
   line where detail was reduced.
3. **In values** — `trunc: true` renders as an explicit `…(truncated)` marker in every view,
   so a truncated array is never mistaken for a short one.

The principle: **the system must always know, and say, what it does not know.** A confident
wrong picture is the one failure mode an educational tool cannot afford.
