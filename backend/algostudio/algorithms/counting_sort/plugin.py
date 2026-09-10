"""Counting Sort -- tally how many times each value occurs, then write the values back in order"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="counting_sort",
    name="Counting Sort",
    category="sorting",
    description=(
                "Tally how many times each value occurs, then write the values back "
        "in order. No comparisons at all. "
    ),
    entry="counting_sort",
    inputs=[
        InputField("arr", "array", default=[4, 2, 2, 8, 3, 3, 1],
                   description="Non-negative values to sort"),
    ],
    complexity=Complexity(time="O(n + k)", space="O(k)",
                          best="O(n + k)", worst="O(n + k)"),
    metrics=['array_reads', 'array_writes'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
        VizHint(target="counts", view="array", weight=0.15),
    ],
    invariants=[
        "sum(counts) always equals len(arr).",
    ],
    tags=['non-comparison', 'linear', 'integer-keys'],
    annotated=False,
)
