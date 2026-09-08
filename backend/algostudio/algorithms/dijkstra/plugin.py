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
