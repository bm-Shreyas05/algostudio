"""Cycle Detection -- three-colour dfs: an edge back into a node still being explored means a cycle"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="cycle_detection",
    name="Cycle Detection",
    category="graph",
    description=(
                "Three-colour DFS: an edge back into a node still being explored "
        "means a cycle. "
    ),
    entry="detect_cycle",
    inputs=[
        InputField("graph", "graph", default={'A': ['B'], 'B': ['C'], 'C': ['A'], 'D': ['C']},
                   description="A directed graph"),
    ],
    complexity=Complexity(time="O(V + E)", space="O(V)",
                          best="O(V + E)", worst="O(V + E)"),
    metrics=['function_calls', 'conditions'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="state", view="table", weight=0.15),
    ],
    invariants=[
        "state is 0 unvisited, 1 on the current path, 2 fully explored.",
    ],
    tags=['traversal', 'recursion', 'dag-check'],
    annotated=False,
)
