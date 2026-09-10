"""Prim's Minimum Spanning Tree -- grow a tree from one node, always taking the cheapest edge that reaches somewhere new"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="prim_mst",
    name="Prim's Minimum Spanning Tree",
    category="graph",
    description=(
                "Grow a tree from one node, always taking the cheapest edge that "
        "reaches somewhere new. "
    ),
    entry="prim",
    inputs=[
        InputField("graph", "weighted_graph", default={'A': [['B', 2], ['D', 6]], 'B': [['A', 2], ['C', 3], ['D', 8], ['E', 5]], 'C': [['B', 3], ['E', 7]], 'D': [['A', 6], ['B', 8], ['E', 9]], 'E': [['B', 5], ['C', 7], ['D', 9]]},
                   description="Undirected weighted adjacency map"),
        InputField("start", "node", default='A',
                   description="Node to grow from"),
    ],
    complexity=Complexity(time="O(E log V)", space="O(V)",
                          best="O(E log V)", worst="O(E log V)"),
    metrics=['enqueues', 'dequeues', 'visits'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
    ],
    invariants=[
        "The chosen edges always form a tree over the visited set.",
    ],
    tags=['greedy', 'mst', 'priority-queue'],
    annotated=False,
)
