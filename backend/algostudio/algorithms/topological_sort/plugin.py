"""Topological Sort -- kahn's algorithm: repeatedly take a node with no remaining prerequisites, and remove its outgoing edges"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="topological_sort",
    name="Topological Sort",
    category="graph",
    description=(
                "Kahn's algorithm: repeatedly take a node with no remaining "
        "prerequisites, and remove its outgoing edges. "
    ),
    entry="topological_sort",
    inputs=[
        InputField("graph", "graph", default={'shirt': ['tie', 'belt'], 'tie': ['jacket'], 'belt': ['jacket'], 'pants': ['belt', 'shoes'], 'socks': ['shoes'], 'jacket': [], 'shoes': []},
                   description="A directed acyclic graph"),
    ],
    complexity=Complexity(time="O(V + E)", space="O(V)",
                          best="O(V + E)", worst="O(V + E)"),
    metrics=['enqueues', 'dequeues'],
    viz_hints=[
        VizHint(target="graph", view="graph", weight=0.2),
        VizHint(target="indegree", view="table", weight=0.15),
    ],
    invariants=[
        "A node is enqueued exactly when its indegree reaches zero.",
        "If the output is shorter than the graph, there was a cycle.",
    ],
    tags=['ordering', 'dag', 'queue'],
    annotated=False,
)
