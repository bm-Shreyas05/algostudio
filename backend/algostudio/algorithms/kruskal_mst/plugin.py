"""Kruskal's Minimum Spanning Tree -- sort every edge by weight and take each one that does not close a cycle, using union-find to tell"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="kruskal_mst",
    name="Kruskal's Minimum Spanning Tree",
    category="graph",
    description=(
                "Sort every edge by weight and take each one that does not close a "
        "cycle, using union-find to tell. "
    ),
    entry="kruskal",
    inputs=[
        InputField("graph", "weighted_graph", default={'A': [['B', 2], ['D', 6]], 'B': [['A', 2], ['C', 3], ['D', 8], ['E', 5]], 'C': [['B', 3], ['E', 7]], 'D': [['A', 6], ['B', 8], ['E', 9]], 'E': [['B', 5], ['C', 7], ['D', 9]]},
                   description="Undirected weighted adjacency map"),
    ],
    complexity=Complexity(time="O(E log E)", space="O(V)",
                          best="O(E log E)", worst="O(E log E)"),
    metrics=['comparisons', 'function_calls'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="parent", view="table", weight=0.15),
    ],
    invariants=[
        "Two nodes share a root exactly when they are already connected.",
    ],
    tags=['greedy', 'mst', 'union-find', 'sorting'],
    annotated=False,
)
