"""Write the reference algorithm plugins.

Each plugin exists to prove a specific architectural property; the docstring in
its ``explain.md`` says which.  Between them they cover annotated and
un-annotated sources, so the demo can show that both paths produce the same
kind of visualization.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "algostudio" / "algorithms"

# The three-line guard lets an annotated source still run as plain Python
# outside AlgoStudio -- a property worth keeping, since plugins are supposed to
# be ordinary code.
GUARD = '''try:                      # `algo` is injected by AlgoStudio at run time
    algo
except NameError:         # ...and this keeps the file runnable as plain Python
    from algostudio.runtime.semantic import null as algo
'''

PLUGINS: dict[str, dict[str, str]] = {}


def plugin(pid: str, meta: str, source: str, explain: str) -> None:
    PLUGINS[pid] = {"plugin.py": meta.strip() + "\n",
                    "source.py": source.strip() + "\n",
                    "explain.md": explain.strip() + "\n"}


# ======================================================================
plugin(
    "binary_search",
    '''
"""Binary Search -- proves pointer/region annotation and branch visualization."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="binary_search",
    name="Binary Search",
    category="search",
    description=(
        "Find a target in a sorted array by repeatedly halving the search "
        "window. Annotated with algo.pointer/algo.region so the array view "
        "shows low, mid and high explicitly."
    ),
    entry="binary_search",
    inputs=[
        InputField("arr", "array", default=[1, 3, 5, 7, 9, 11, 13, 15, 17, 19],
                   description="A sorted list of numbers"),
        InputField("target", "int", default=13, description="Value to find"),
    ],
    complexity=Complexity(time="O(log n)", space="O(1)",
                          best="O(1)", worst="O(log n)"),
    metrics=["comparisons", "loop_iterations"],
    viz_hints=[VizHint(target="arr", view="array", weight=0.15)],
    invariants=[
        "If the target is present, its index is always within [low, high].",
        "The search window at least halves on every iteration.",
    ],
    tags=["divide-and-conquer", "sorted-input", "iterative"],
    annotated=True,
)
''',
    GUARD + '''

def binary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        algo.region(arr, low, high, "search window")
        mid = (low + high) // 2
        algo.pointer(arr, mid, "mid")
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
''',
    """
# Binary Search

**Proves:** pointer and region annotations, and branch visualization on a
three-way comparison.

The `algo.pointer` and `algo.region` calls are *optional*. Remove them and the
pointer lifter still recovers `low`, `mid` and `high` from the generic event
stream, because each is an integer variable used as a subscript index. Try it:
paste this source into the editor with the annotations deleted and compare.

**Invariant.** If the target is in the array, its index is always inside
`[low, high]`. Every iteration discards half the remaining window, so the loop
runs at most `floor(log2(n)) + 1` times.
""",
)

# ======================================================================
plugin(
    "merge_sort",
    '''
"""Merge Sort -- proves that divide-and-conquer needs no special support."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="merge_sort",
    name="Merge Sort",
    category="sorting",
    description=(
        "Recursively split the array, sort each half, and merge. Deliberately "
        "un-annotated: the call tree and the sub-array views are derived "
        "entirely from generic function and container events."
    ),
    entry="merge_sort",
    inputs=[
        InputField("arr", "array", default=[38, 27, 43, 3, 9, 82, 10],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n log n)", space="O(n)",
                          best="O(n log n)", worst="O(n log n)"),
    metrics=["comparisons", "array_writes", "function_calls", "max_depth"],
    viz_hints=[VizHint(target="arr", view="array", weight=0.15)],
    invariants=[
        "Each recursive call returns a sorted list.",
        "Merging two sorted lists of total length k costs at most k-1 comparisons.",
    ],
    tags=["divide-and-conquer", "stable", "recursive"],
    annotated=False,
)
''',
    '''
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)


def merge(left, right):
    out = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    while i < len(left):
        out.append(left[i])
        i += 1
    while j < len(right):
        out.append(right[j])
        j += 1
    return out
''',
    """
# Merge Sort

**Proves:** a divide-and-conquer algorithm needs no special support.

There is not a single `algo.*` call in this source, and no merge-sort-specific
code anywhere in the platform. The recursion tree comes from `FUNCTION_ENTERED`
and `FUNCTION_EXITED` events via the generic call-tree view; the sub-array
slices are ordinary heap objects that the scalar-array detector recognises; the
comparison count comes from comparison events.

**Invariant.** Every recursive call returns a sorted list, so `merge` only ever
combines two sorted inputs.
""",
)

# ======================================================================
plugin(
    "bubble_sort",
    '''
"""Bubble Sort -- proves swap lifting from completely un-annotated code."""

from algostudio.plugins.base import AlgorithmPlugin, Complexity, InputField

PLUGIN = AlgorithmPlugin(
    id="bubble_sort",
    name="Bubble Sort",
    category="sorting",
    description=(
        "Repeatedly swap adjacent out-of-order elements. Contains no "
        "annotations whatsoever: every swap and comparison in the "
        "visualization was inferred from the raw event stream."
    ),
    entry="bubble_sort",
    inputs=[
        InputField("arr", "array", default=[5, 2, 9, 1, 7, 3],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(1)",
                          best="O(n)", worst="O(n^2)"),
    metrics=["comparisons", "swaps", "loop_iterations"],
    invariants=[
        "After pass i, the last i elements are in their final positions.",
    ],
    tags=["comparison-sort", "in-place", "stable", "quadratic"],
    annotated=False,
)
''',
    '''
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr
''',
    """
# Bubble Sort

**Proves:** semantic events can be recovered from code nobody annotated.

This is the most important plugin in the set, precisely because it is the least
interesting algorithm. There are no `algo.*` calls. The `SWAP` events you see in
the timeline were produced by `SwapLifter`, which matched a structural pattern:
two subscript writes to the same container, at different indices, within one
statement, whose values exchange. It has never heard of bubble sort, and it
fires the same way on a partition step in quick sort or on a student's own code.

**Invariant.** After pass `i`, the last `i` elements are in their final places.
""",
)

# ======================================================================
plugin(
    "bfs",
    '''
"""BFS -- proves graph views come from data structure, not algorithm identity."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

DEFAULT_GRAPH = {
    "A": ["B", "C"],
    "B": ["D", "E"],
    "C": ["F"],
    "D": [],
    "E": ["F"],
    "F": ["G"],
    "G": [],
}

PLUGIN = AlgorithmPlugin(
    id="bfs",
    name="Breadth-First Search",
    category="graph",
    description=(
        "Explore a graph level by level using a queue. The graph view is "
        "chosen because the input is a dict whose value elements are its own "
        "keys -- no graph-specific code is involved."
    ),
    entry="bfs",
    inputs=[
        InputField("graph", "graph", default=DEFAULT_GRAPH,
                   description="Adjacency map: node -> list of neighbours"),
        InputField("start", "node", default="A", description="Starting node"),
    ],
    complexity=Complexity(time="O(V + E)", space="O(V)"),
    metrics=["visits", "enqueues", "dequeues"],
    viz_hints=[VizHint(target="graph", view="graph", weight=0.2)],
    invariants=[
        "Nodes are dequeued in non-decreasing order of distance from the start.",
        "Every node is enqueued at most once.",
    ],
    tags=["traversal", "queue", "unweighted"],
    annotated=False,
)
''',
    '''
from collections import deque


def bfs(graph, start):
    visited = set()
    order = []
    distance = {}
    queue = deque()
    queue.append(start)
    visited.add(start)
    distance[start] = 0
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in graph[node]:
            if neighbour not in visited:
                visited.add(neighbour)
                distance[neighbour] = distance[node] + 1
                queue.append(neighbour)
    return order
''',
    """
# Breadth-First Search

**Proves:** the graph view is chosen from the *shape of the data*.

Nothing here declares "this is a graph". `AdjacencyMapDetector` sees a dict
whose value elements are drawn from its own key set and proposes a graph view
with high confidence; the `visited` set and the `distance` dict get their own
views by the same route. The queue panel is fed by `StackQueueLifter`, which
recognises `deque.append` / `deque.popleft` as enqueue/dequeue.

Change the input to any other adjacency map -- including one for a graph
algorithm the platform has never run -- and the same thing happens.

**Invariant.** Nodes leave the queue in non-decreasing distance order, which is
why BFS finds shortest paths in unweighted graphs.
""",
)

# ======================================================================
plugin(
    "dijkstra",
    '''
"""Dijkstra -- proves heterogeneous simultaneous views and relaxation lifting."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

DEFAULT_GRAPH = {
    "A": [["B", 4], ["C", 2]],
    "B": [["C", 5], ["D", 10]],
    "C": [["E", 3]],
    "D": [["F", 11]],
    "E": [["D", 4]],
    "F": [],
}

PLUGIN = AlgorithmPlugin(
    id="dijkstra",
    name="Dijkstra's Shortest Path",
    category="graph",
    description=(
        "Single-source shortest paths on a graph with non-negative weights, "
        "using a priority queue. Shows three views at once: the graph, the "
        "distance table, and the heap."
    ),
    entry="dijkstra",
    inputs=[
        InputField("graph", "weighted_graph", default=DEFAULT_GRAPH,
                   description="node -> list of [neighbour, weight] pairs"),
        InputField("source", "node", default="A", description="Source node"),
    ],
    complexity=Complexity(time="O((V + E) log V)", space="O(V)"),
    metrics=["visits", "relaxations", "enqueues", "dequeues"],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="dist", view="table", weight=0.15),
    ],
    invariants=[
        "Once a node is popped from the queue its distance is final.",
        "dist[v] is always the length of some known path to v.",
    ],
    tags=["greedy", "shortest-path", "priority-queue", "weighted"],
    annotated=True,
)
''',
    GUARD + '''
import heapq

INF = float("inf")


def dijkstra(graph, source):
    dist = {}
    for node in graph:
        dist[node] = INF
    dist[source] = 0
    visited = set()
    heap = []
    heapq.heappush(heap, (0, source))
    while heap:
        pair = heapq.heappop(heap)
        d = pair[0]
        u = pair[1]
        if u in visited:
            continue
        visited.add(u)
        algo.visit(u)
        for edge in graph[u]:
            v = edge[0]
            w = edge[1]
            candidate = d + w
            improved = candidate < dist[v]
            algo.relax(u, v, w, improved)
            if improved:
                dist[v] = candidate
                heapq.heappush(heap, (candidate, v))
    return dist
''',
    """
# Dijkstra's Shortest Path

**Proves:** heterogeneous simultaneous views, and that a hint biases rather than
forces view selection.

Three views appear at once and are kept in sync by the timeline: the graph
(from the adjacency detector), the distance table (from the mapping detector),
and the priority queue (from the heap detector, which requires *both* the heap
property to hold *and* the list to have been mutated by heap operations -- a
list that merely happens to be heap-ordered is not a heap).

The `viz_hints` in `plugin.py` add at most 0.3 to a view's score and only to
views a detector already proposed. Delete them and the same three views are
selected; they only break ties.

`algo.visit` and `algo.relax` are explicit here, but `RelaxLifter` recovers
relaxations from un-annotated code too -- it matches any conditional
improvement of a keyed distance, which is why it also fires inside Bellman-Ford
and in dynamic-programming code that has nothing to do with graphs.

**Invariant.** Once a node is popped, its distance is final. This is what fails
when edge weights can be negative.
""",
)


def main() -> int:
    for pid, files in PLUGINS.items():
        directory = ROOT / pid
        directory.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (directory / name).write_text(content, encoding="utf-8")
    print(f"wrote {len(PLUGINS)} plugins to {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
