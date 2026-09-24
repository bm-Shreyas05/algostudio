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
        "Explore a graph level by level with a queue, visiting every node reachable from the start."
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
