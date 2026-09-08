# 07 — Algorithm Plugin Architecture & Semantic Events

*(Deliverables M; §12 and §13 of the brief)*

---

## M.1 The core constraint

> Adding an algorithm must change **zero** files outside `algorithms/<name>/`.

This is INV-1 and it is mechanically tested. The design follows directly from taking it
seriously.

Anything that would require the core to *know* about the algorithm is forbidden:
no registry file to edit, no enum to extend, no `switch` in the renderer, no
algorithm-specific view component, no algorithm-specific analytics counter.

---

## M.2 What a plugin is

A plugin is **a directory containing metadata and ordinary source code**.

```
algorithms/dijkstra/
├── plugin.py        # PLUGIN = AlgorithmPlugin(...)  — pure data
├── source.py        # the algorithm, as a student would write it
└── explain.md       # optional educational prose
```

```python
# plugin.py
from algostudio.plugins.base import AlgorithmPlugin, InputField, Complexity, VizHint

PLUGIN = AlgorithmPlugin(
    id="dijkstra",
    name="Dijkstra's Shortest Path",
    category="graph",
    description="Single-source shortest paths on a non-negative weighted graph.",
    entry="dijkstra",                       # function to call in source.py
    inputs=[
        InputField("graph", "graph", default={...}, description="adjacency map"),
        InputField("source", "node", default="A"),
    ],
    complexity=Complexity(time="O((V+E) log V)", space="O(V)",
                          best="O((V+E) log V)", worst="O((V+E) log V)"),
    metrics=["visit", "relax", "enqueue", "dequeue"],
    viz_hints=[VizHint(target="graph", view="graph", weight=0.3),
               VizHint(target="dist",  view="table", weight=0.2)],
    invariants=["dist[u] is final once u is popped from the priority queue"],
    tags=["greedy","shortest-path","priority-queue"],
)
```

The critical property: **`source.py` is executed by exactly the same pipeline as user-typed
code.** There is no privileged execution path, no special-cased tracer, no bypass. Running
the packaged Dijkstra and running Dijkstra pasted into the editor produce byte-identical
event streams (modulo the module name). This is not an implementation detail — it is the
proof that the platform is not a disguised animation library, and it is asserted by
`tests/test_plugin_source_parity.py`.

Discovery is a filesystem scan: `algorithms/*/plugin.py`, import, read `PLUGIN`. No
central registration list exists to be edited. A plugin dropped into the directory appears
in the catalog on next start (or immediately, in dev, via the registry's mtime check).

### What each declared field is actually used for

| Field | Consumer | Binding force |
|---|---|---|
| `inputs` | UI form generation, input validation, benchmark harness | authoritative |
| `complexity` | analytics panel (plots measured ops against the stated bound), AI context | informational |
| `metrics` | analytics panel column selection | informational |
| `viz_hints` | **bias** to the view resolver's score | advisory only |
| `invariants` | educational mode, AI prompt | informational |
| `entry` | how to call the source | authoritative |

`viz_hints` being *advisory* is the design decision that preserves the core claim. A hint
adds `weight` to a view's score; it cannot select a view that the structural detectors did
not already propose. Consequence: **student-typed Dijkstra gets the same graph view as
plugin Dijkstra**, because the graph view was chosen by looking at the data, not at the
hint. The hint only breaks ties.

---

## M.3 Semantic events: the two-mechanism design

§12 of the brief identifies the real problem: `arr[i], arr[j] = arr[j], arr[i]` produces
several low-level writes, but the *meaningful* unit is one `SWAP`. Forcing the renderer to
infer that would put algorithm knowledge in the renderer.

The solution uses **two independent mechanisms that produce identical events**.

### Mechanism 1 — explicit annotation (`algo.*`)

A small object named `algo` is injected into every program's globals. Any code — plugin or
student — may call it:

```python
def bubble_sort(arr):
    for i in range(len(arr)):
        for j in range(len(arr) - i - 1):
            if algo.compare(arr[j], arr[j+1]) > 0:      # emits ALGORITHM_EVENT(compare)
                algo.swap(arr, j, j+1)                   # emits ALGORITHM_EVENT(swap) + does it
```

API surface (all no-ops if the runtime is absent, so annotated code still runs outside
AlgoStudio — an important property for plugin sources that must remain plain Python):

```python
algo.compare(a, b) -> int          # emits compare, returns -1/0/1
algo.swap(seq, i, j)               # performs and emits the swap
algo.visit(node, **kw)             # graph/tree traversal
algo.discover(node, via=None)
algo.relax(u, v, weight, improved) # Dijkstra/Bellman-Ford edge relaxation
algo.enqueue(q, x) / algo.dequeue(q) -> x
algo.push(s, x) / algo.pop(s) -> x
algo.pointer(seq, index, label)    # named pointer annotation, e.g. "mid"
algo.region(seq, lo, hi, label)    # highlighted sub-range, e.g. "search window"
algo.mark(target, label, color)    # persistent mark
algo.note(text)                    # free-form annotation on the timeline
algo.metric(name, delta=1)         # custom counter
```

Cost: requires the code to be annotated. That is fine for plugins, and available but not
required for students.

### Mechanism 2 — lifting (pattern recognition over generic events)

A **lifter** is a small state machine consuming the raw event stream and emitting
`ALGORITHM_EVENT`s. It matches **structural patterns, never algorithm identity**.

```python
class Lifter(Protocol):
    id: str
    window: int                                   # max events of lookahead needed
    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]: ...
```

Built-in lifters:

| Lifter | Pattern it matches | Emits |
|---|---|---|
| `SwapLifter` | two `SUBSCRIPT_WRITTEN` on the same `container_ref` at indices i,j within one statement where `new_i == old_j` and `new_j == old_i` (also the tuple-assignment and temp-variable forms) | `swap(ref,i,j)` |
| `CompareLifter` | `COMPARE`/`CONDITION_EVALUATED` whose operands both derive from `SUBSCRIPT_READ` on the same container | `compare(ref,i,j,result)` |
| `PointerLifter` | an int-valued variable used as a subscript index into a container in the current statement | `pointer(ref, value, name)` |
| `StackQueueLifter` | `OBJECT_MUTATED` with op in `{append,pop}` / `{append,pop(0)}` / `{deque.append,popleft}` | `push`/`pop`/`enqueue`/`dequeue` |
| `RelaxLifter` | write to `d[v]` guarded by a condition comparing `d[v]` with `d[u] + w` | `relax(u,v,w,improved)` |
| `VisitLifter` | insertion into a container the shape detectors classify as a *visited set*, keyed on a node identifier also used as a graph key | `visit(node)` |
| `RegionLifter` | two int variables bracketing a container that both monotonically converge | `region(ref, lo, hi)` |

**Why this is not "hard-coding algorithms":** `RelaxLifter` does not know what Dijkstra is.
It fires on any conditional distance improvement — in Bellman-Ford, in Floyd-Warshall's
inner loop, in a student's own shortest-path attempt, in a dynamic-programming relaxation
that has nothing to do with graphs. Lifters are *idiom* recognizers, and idioms are
cross-algorithm by definition. The distinction I hold to is:

> Matching on **the shape of what the program did** is derivation.
> Matching on **the name of the algorithm** is hard-coding.

Every lifter output carries `meta.origin = "lifted"` and `meta.confidence`. The UI can
show lifted events differently, and a user can disable the lifter pipeline entirely — in
which case the visualization degrades to generic array/variable views rather than breaking.
That switch is also the ablation for RQ1.

### Why keep both mechanisms

| | explicit `algo.*` | lifting |
|---|---|---|
| works on unmodified student code | no | **yes** |
| precise, no false positives | **yes** | no (confidence-scored) |
| requires learning an API | yes | **no** |
| survives refactoring | yes | mostly |
| available to future languages | needs a per-language binding | **yes** (works on events) |

They cover each other's weaknesses, and because they emit the same event type, everything
downstream — views, analytics, AI, timeline — has exactly one code path.

---

## M.4 Plugin lifecycle

```
registry.discover()                    scan algorithms/*/plugin.py
registry.validate(p)                   schema check; source parses; entry exists;
                                       source passes the capability checker
GET /api/v1/algorithms                 catalog for the UI (metadata only)
POST /api/v1/algorithms/{id}/run       inputs validated against InputField schema
   -> render a driver module:
        from source import <entry>
        result = <entry>(**inputs)      # bound values injected as literals or via a loader
   -> the standard pipeline: instrument -> sandbox -> lift -> reduce -> analyze
```

The driver module is generated from a template; the plugin author does not write it. Inputs
are materialized inside the sandbox by a small loader so that large inputs (a 1000-element
array) are not embedded as source literals.

### Validation is real

`registry.validate` runs the plugin's `source.py` through the **capability checker**. A
plugin using an unsupported construct is rejected at startup with a precise message, rather
than failing mysteriously at run time. Plugins are held to the same support boundary as
user code — because they *are* user code.

---

## M.5 The four reference plugins, and what each is chosen to prove

| Plugin | Proves |
|---|---|
| **Binary Search** | pointer + region annotations; a *linear* array view with converging bounds; branch visualization on a three-way comparison |
| **Merge Sort** | recursion + call tree; array views of *sub-slices*; that a divide-and-conquer algorithm needs no special support |
| **BFS** | graph shape detection from an adjacency dict; queue view driven by `StackQueueLifter`; visited-set annotation |
| **Dijkstra** | heterogeneous simultaneous views (graph + distance table + priority queue); `RelaxLifter`; that a hint biases but does not force view selection |
| *(bonus)* **Bubble Sort** | the swap lifter on *unannotated* code, and the comparison benchmark against Merge Sort |
| *(demo)* **user-typed algorithm** | INV-1 — a never-before-seen algorithm gets full visualization with zero platform changes |

The last row is the demo scenario the brief calls "VERY important" (§34.7), and the whole
architecture exists to make it work.

---

## M.6 Extension points summary

| To add... | You write | Core files changed |
|---|---|---|
| an algorithm | `algorithms/<id>/{plugin.py,source.py}` | **0** |
| a semantic idiom | `lifters/<name>.py` + register in the pipeline list | 1 (the pipeline list) |
| a data-structure view | `frontend/src/views/<Name>View.tsx` + a detector in `shapes/detectors.py` | 2 (two registries) |
| a language | `languages/<lang>/frontend.py` | 1 (the frontend registry) |
| an event type | `core/events.py` + a reducer handler | 2 |

The three "1 or 2 file" cases are all *registry list* edits. That is the irreducible
minimum for a system without runtime plugin discovery for every subsystem, and it is honest
to state it rather than claiming zero everywhere. Only the **algorithm** case — the one the
project's claim is about — is genuinely zero.
