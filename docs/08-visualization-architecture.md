# 08 — Visualization Architecture

*(Deliverable N; §7–§11, §20, §28 of the brief)*

---

## N.1 The forbidden pattern, and what replaces it

```tsx
// FORBIDDEN — and CI-enforced
if (algorithm === "bubble_sort") return <BubbleSortView .../>
```

Replaced by a three-stage pipeline in which the renderer never learns an algorithm's name:

```
ExecutionState
    │
    ├─► [1] SHAPE DETECTION      heap object -> [ShapeMatch{view, score, props}]
    │        (backend, shapes/detectors.py — structural predicates only)
    │
    ├─► [2] VIEW RESOLUTION      ShapeMatch[] + VizHint[] + user override
    │                            -> [ViewDescriptor] (ordered layout plan)
    │
    └─► [3] RENDER               ViewRegistry.get(descriptor.view) -> React component
                                 component receives (heapObject, annotations, state)
```

Stage 1 produces *claims about structure*. Stage 2 arbitrates. Stage 3 draws. No stage
receives an algorithm identifier at any point.

---

## N.2 Stage 1 — shape detection

A detector is a pure function `HeapObject × ExecutionState → ShapeMatch | None`.

```python
@dataclass
class ShapeMatch:
    view: str            # "array" | "graph" | "tree" | "table" | "matrix" | ...
    score: float         # 0..1 structural confidence
    props: dict          # view-specific derived props (e.g. inferred node/edge lists)
    reason: str          # human-readable, shown in the UI's "why this view?" tooltip
```

Built-in detectors and their **purely structural** predicates:

| Detector | Predicate | Emits |
|---|---|---|
| `ScalarArray` | list/tuple, len ≥ 2, ≥ 80% numeric or all-string elements | `array` 0.7 |
| `Matrix2D` | list of lists, all inner lengths equal, len ≥ 2, numeric | `matrix` 0.85 |
| `AdjacencyMap` | dict whose values are lists/sets/dicts and where ≥ 60% of the value elements are themselves keys of the same dict | `graph` 0.9 |
| `EdgeList` | list of 2- or 3-tuples where the first two components are drawn from a small repeated domain | `graph` 0.7 |
| `AdjacencyMatrix` | square numeric matrix, ≥ 60% zeros, symmetric or DAG-consistent | `graph` 0.6 |
| `LinkedStructure` | object with a field referencing an object of the same class; single such field -> `linked-list`, exactly two (`left`/`right`, `l`/`r`, `children`) -> `tree` | `tree` / `linked-list` 0.85 |
| `NestedListTree` | list of `[value, [children...]]` or dict with a `children` key | `tree` 0.7 |
| `HeapArray` | numeric list that satisfies the heap property at the current step **and** whose recent mutations came from `heapq.*` calls | `heap` 0.75 |
| `KeyValueTable` | dict with scalar values, len ≥ 2 | `table` 0.6 |
| `SetView` | set/frozenset | `set` 0.6 |
| `StackLike` | list mutated only by `append`/`pop()` (no index writes) over the run | `stack` 0.65 |
| `QueueLike` | `deque`, or list mutated by `append`/`pop(0)` | `queue` 0.7 |
| `Fallback` | anything | `object` 0.1 |

Three design points worth defending:

1. **Detectors run per-step but decisions are sticky.** Re-detecting every step would make
   the view flicker (an empty list is not yet an array). The resolver computes a *stable*
   assignment using the **whole-execution** heap history, so `visited = set()` is rendered
   as a set from step 0, not from the step it first becomes non-empty. Detection at the
   final state, applied to all steps.

2. **`HeapArray` and `StackLike` use mutation history, not just current contents.** A list
   that happens to satisfy the heap property is not a heap; a list that `heapq` pushed into
   is. This is why detectors take `ExecutionState` and not just the object — and it is the
   only place where events (not just state) influence view choice.

3. **Detectors are additive and non-exclusive.** One object can produce several matches; the
   UI offers all of them in a "view as" switcher with the winner preselected. Users can
   override, and the override is remembered per (execution, ref).

---

## N.3 Stage 2 — view resolution

```
final_score(view, obj) = max(detector scores for view)
                       + Σ hint.weight  for hints targeting obj/view
                       + 0.5            if the user pinned this view
                       + 0.15           if annotations reference obj (it is "active")
                       - 0.3            if obj is unreferenced by any live binding
```

Layout plan: objects sorted by `final_score × liveness`, top N (default 3) placed in the
main canvas, the rest available as tabs. "Liveness" = referenced by a binding in an active
frame, weighted by recency of mutation. This means the canvas automatically foregrounds
*the array currently being sorted* rather than a stale copy — again from state structure,
not algorithm knowledge.

**Hints cannot create a view.** `Σ hint.weight` is capped at 0.3 and applies only to views
that already have a detector match > 0. This is the mechanical guarantee behind "the same
code typed by a student gets the same visualization".

---

## N.4 Stage 3 — the view contract

Every view component receives the same props and nothing else:

```ts
interface ViewProps {
  object:      HeapObject;              // the resolved object
  heap:        Record<Ref, HeapObject>; // for following refs
  annotations: Annotation[];            // pointers, marks, regions targeting this object
  state:       ExecutionState;          // read-only, for context (current frame etc.)
  props:       Record<string, unknown>; // detector-derived (e.g. computed node/edge lists)
  onSelect:    (ref: Ref, path?: (string|number)[]) => void;
}
```

Notice what is absent: the algorithm id, the plugin, the source, the event stream. A view
cannot depend on them because it is not given them.

### Registered views

| View | Renders | Annotation handling |
|---|---|---|
| `ArrayView` | horizontal cells with index ruler; bar-height mode for numeric | pointers as labelled carets under cells; regions as tinted spans; `swap` events animate a position exchange; `compare` pulses two cells |
| `MatrixView` | grid with row/col headers; heat-map mode | cell marks, row/col highlights |
| `GraphView` | SVG, deterministic layout (circular seed + 250 force ticks, seeded so layout is stable across steps and reloads) | node marks (visited/frontier/current), edge highlight on `relax`, edge labels for weights |
| `TreeView` | tidy layered layout (Reingold–Tilford style), edges as curves | node marks; recursion-tree mode when fed the call tree |
| `LinkedListView` | node boxes + next arrows; detects cycles | pointer annotations |
| `TableView` / `DictView` | key/value rows, changed rows flash | key marks |
| `SetView` | chip cloud, insertion-ordered | membership marks |
| `StackView` / `QueueView` | vertical / horizontal with in/out ends labelled | top/front markers |
| `HeapView` | binary tree over the array **plus** the backing array, index-linked | both representations share annotations |
| `ObjectView` | field table with ref arrows | — |
| `CallTreeView` | the recursion tree built from `FUNCTION_ENTERED/EXITED` events | current path highlighted |

`CallTreeView` deserves comment: the Fibonacci recursion tree the brief asks for (§10) is
**not** a Fibonacci feature. It is the generic call tree, which for `fib(5)` happens to
look like the familiar diagram. `quick_sort` produces its own shape from the same
component. That is the property being demonstrated.

---

## N.5 Panels (fixed, not resolved)

Views are dynamic; **panels** are static IDE furniture.

| Panel | Source of truth | Notes |
|---|---|---|
| **SourceView** | `source` + `state.current_loc` + `analytics.line_hits` | current line highlighted; executed lines tinted by hit count (a cheap heat map that makes dead branches obvious); breakpoint gutter; click a line -> jump to its next execution; the *taken* branch of an `if` is underlined using `BRANCH_TAKEN` |
| **VariablesPanel** | `state.frames[active].locals` + `state.globals` | change flash on write; `old -> new` shown for one step; click a variable -> filter the timeline to its events (this is §8's "where was it modified") |
| **CallStackPanel** | `state.frames` | click a frame -> switch the inspected frame without moving the execution pointer |
| **Timeline** | `[EventSummary]` | virtualized; grouped by loop iteration and by call; filter chips per event category; search; collapse of repetitive events (see below) |
| **Console** | `state.stdout/stderr` | truncated to the current step — output "un-prints" when stepping back, which is a small detail that makes time travel feel real |
| **AnalyticsPanel** | `analytics` | counters, per-line heat, complexity curve |
| **AIPanel** | `/ai` | question box + preset modes; shows the grounding report |
| **CapabilityBanner** | `capability_report` | shows any `INSTRUMENTATION_SKIPPED` lines |

### Timeline collapsing (§20)

Raw event counts are large. The timeline builds a **tree**, not a list:

```
▾ main()                                     frame 0
  ▾ for i in range(3)               line 2   loop L1, 3 iterations
    ▸ iteration 0                            12 events   [x: 5 → 5]
    ▸ iteration 1                            12 events   [x: 5 → 6]
    ▾ iteration 2                            12 events   [x: 6 → 8]
        LINE 3
        VARIABLE_READ  x = 6
        SWAP  arr[1] ↔ arr[2]
```

Grouping keys are `loop_id + iteration` and `frame`, both already in the envelope. Rows
show a one-line *effect summary* derived from the group's mutating events, so a collapsed
iteration still tells you what it did. Repetitive sibling groups with identical effect
shapes collapse into "×12 similar iterations" with an expand affordance.

---

## N.6 Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ AlgoStudio   [algorithm ▾]  ▶ Run  ⏸  ⏮ ⏪ ⏩ ⏭   ▰▱▱ speed   ⚙  AI          │
├──────────────────────┬─────────────────────────────────┬─────────────────────┤
│ SOURCE               │ VISUALIZATION CANVAS            │ VARIABLES           │
│  1 def bsearch(a,t): │  ┌───────────────────────────┐  │  low   = 0          │
│  2   low = 0         │  │ arr  [1][3][5][7][9]      │  │  high  = 4          │
│ ▶3   high = len(a)-1 │  │       ▲lo      ▲mid  ▲hi  │  │  mid   = 2  ← 1     │
│  4   while low<=high │  └───────────────────────────┘  ├─────────────────────┤
│  5     mid = ...     │  ┌───────────────────────────┐  │ CALL STACK          │
│                      │  │ dist {A:0, B:4, C:∞}      │  │  bsearch(a,t)  L5   │
│                      │  └───────────────────────────┘  │  <module>      L12  │
├──────────────────────┴─────────────────────────────────┴─────────────────────┤
│ TIMELINE  ▾main ▾while-loop  ▸it0  ▸it1  ▾it2 [COMPARE a[2]<7] [WRITE low=3] │
├──────────────────────────────────────────────────────────────────────────────┤
│ CONSOLE  |  ANALYTICS  |  AI TUTOR                                           │
└──────────────────────────────────────────────────────────────────────────────┘
```

Visual language: dark IDE chrome, monospace for code and values, one accent colour for
"current", one for "changed", one for "read". Motion is used only for state *changes*
(a swap animates; a re-render does not), because animation that does not carry information
is noise in an educational tool.

---

## N.7 Client-side data flow

```
WS event batches ──► ExecutionStore.events[]           (append-only)
                            │
                     Timeline (TS mirror of the reducer)
                            │
      ┌─────────────────────┼──────────────────────────┐
  state(step)          analytics(step)            viewPlan(state)
      │                     │                          │
  panels                analytics panel           ViewRegistry -> views
```

Navigation never hits the network. Playback is `requestAnimationFrame` driving
`step_forward` at a configurable events-per-second, with the reducer running on the main
thread (it is a dictionary update per event — profiled at > 500k steps/sec, far above the
~60/sec a human can watch). Executions above `MAX_CLIENT_EVENTS` switch to server-side
`GET /state?step=`, keeping the UI identical.

---

## N.8 Anti-hard-coding enforcement

`tests/test_no_algorithm_names_in_views.py`:

```python
BANNED = ["bubble", "quicksort", "quick_sort", "mergesort", "merge_sort", "dijkstra",
          "bfs", "dfs", "binary_search", "kruskal", "prim", "fibonacci", "astar"]
for path in glob("frontend/src/views/**/*.tsx") + glob("backend/algostudio/shapes/*.py"):
    assert not any(b in read(path).lower() for b in BANNED), path
```

Crude, and deliberately so: it is a *tripwire*, and a reviewer noticing it fire is the point.
The same test also asserts that no file under `views/` imports from `algorithms/`.
