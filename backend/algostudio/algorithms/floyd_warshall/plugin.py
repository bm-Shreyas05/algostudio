"""Floyd-Warshall -- all-pairs shortest paths by asking, for every pair, whether routing through a third node is shorter"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="floyd_warshall",
    name="Floyd-Warshall",
    category="graph",
    description=(
                "All-pairs shortest paths by asking, for every pair, whether routing "
        "through a third node is shorter. "
    ),
    entry="floyd_warshall",
    inputs=[
        InputField("graph", "weighted_graph", default={'A': [['B', 4], ['C', 2]], 'B': [['C', 5], ['D', 10]], 'C': [['E', 3]], 'D': [['F', 11]], 'E': [['D', 4]], 'F': []},
                   description="node -> list of [neighbour, weight]"),
    ],
    complexity=Complexity(time="O(V^3)", space="O(V^2)",
                          best="O(V^3)", worst="O(V^3)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="dist", view="table", weight=0.2),
    ],
    invariants=[
        "After the iteration for k, dist[i][j] uses only intermediates from the first k nodes.",
    ],
    tags=['shortest-path', 'dynamic-programming', 'all-pairs'],
    annotated=False,
)
