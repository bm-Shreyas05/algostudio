"""Union-Find (Disjoint Set) -- merge sets and ask which set something is in, with path compression and union by rank"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="union_find",
    name="Union-Find (Disjoint Set)",
    category="data-structure",
    description=(
                "Merge sets and ask which set something is in, with path compression "
        "and union by rank. "
    ),
    entry="union_find",
    inputs=[
        InputField("pairs", "array", default=[[0, 1], [2, 3], [1, 2], [5, 6]],
                   description="Pairs to union"),
        InputField("size", "int", default=8,
                   description="Number of elements"),
    ],
    complexity=Complexity(time="near O(1) amortised", space="O(n)",
                          best="near O(1) amortised", worst="near O(1) amortised"),
    metrics=['function_calls', 'array_writes'],
    viz_hints=[
        VizHint(target="parent", view="array", weight=0.2),
    ],
    invariants=[
        "Every element points at a parent; following the chain reaches the set's root.",
    ],
    tags=['data-structure', 'amortised', 'path-compression'],
    annotated=False,
)
