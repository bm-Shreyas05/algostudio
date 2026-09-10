"""Connected Components -- repeatedly pick an unvisited node and flood outwards; each flood is one component"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="connected_components",
    name="Connected Components",
    category="graph",
    description=(
                "Repeatedly pick an unvisited node and flood outwards; each flood is "
        "one component. "
    ),
    entry="connected_components",
    inputs=[
        InputField("graph", "graph", default={'A': ['B', 'C'], 'B': ['A', 'D'], 'C': ['A', 'D'], 'D': ['B', 'C', 'E'], 'E': ['D'], 'F': ['G'], 'G': ['F']},
                   description="Adjacency map: node -> neighbours"),
    ],
    complexity=Complexity(time="O(V + E)", space="O(V)",
                          best="O(V + E)", worst="O(V + E)"),
    metrics=['visits', 'pushes', 'pops'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
    ],
    invariants=[
        "Every node ends up in exactly one component.",
    ],
    tags=['traversal', 'connectivity'],
    annotated=False,
)
