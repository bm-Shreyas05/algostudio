"""Bellman-Ford -- relax every edge v-1 times"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="bellman_ford",
    name="Bellman-Ford",
    category="graph",
    description=(
                "Relax every edge V-1 times. Slower than Dijkstra, but it works with "
        "negative edge weights. "
    ),
    entry="bellman_ford",
    inputs=[
        InputField("graph", "weighted_graph", default={'A': [['B', 4], ['C', 2]], 'B': [['C', 5], ['D', 10]], 'C': [['E', 3]], 'D': [['F', 11]], 'E': [['D', 4]], 'F': []},
                   description="node -> list of [neighbour, weight]"),
        InputField("source", "node", default='A',
                   description="Source node"),
    ],
    complexity=Complexity(time="O(V * E)", space="O(V)",
                          best="O(V * E)", worst="O(V * E)"),
    metrics=['relaxations', 'comparisons'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="dist", view="table", weight=0.15),
    ],
    invariants=[
        "After pass k, dist[v] is correct for every path using at most k edges.",
    ],
    tags=['shortest-path', 'dynamic-programming', 'negative-weights'],
    annotated=False,
)
