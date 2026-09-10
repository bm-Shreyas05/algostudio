"""Depth-First Search -- follow one path as deep as it goes before backtracking, using an explicit stack"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="dfs",
    name="Depth-First Search",
    category="graph",
    description=(
                "Follow one path as deep as it goes before backtracking, using an "
        "explicit stack. "
    ),
    entry="dfs",
    inputs=[
        InputField("graph", "graph", default={'A': ['B', 'C'], 'B': ['A', 'D'], 'C': ['A', 'D'], 'D': ['B', 'C', 'E'], 'E': ['D'], 'F': ['G'], 'G': ['F']},
                   description="Adjacency map: node -> neighbours"),
        InputField("start", "node", default='A',
                   description="Starting node"),
    ],
    complexity=Complexity(time="O(V + E)", space="O(V)",
                          best="O(V + E)", worst="O(V + E)"),
    metrics=['visits', 'pushes', 'pops'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
    ],
    invariants=[
        "Every node on the stack has been discovered but not yet expanded.",
    ],
    tags=['traversal', 'stack'],
    annotated=False,
)
