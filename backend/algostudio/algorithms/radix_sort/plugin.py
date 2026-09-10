"""Radix Sort -- sort by each digit position in turn, using a stable counting pass per digit"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="radix_sort",
    name="Radix Sort",
    category="sorting",
    description=(
                "Sort by each digit position in turn, using a stable counting pass "
        "per digit. "
    ),
    entry="radix_sort",
    inputs=[
        InputField("arr", "array", default=[170, 45, 75, 90, 802, 24, 2, 66],
                   description="Non-negative values"),
    ],
    complexity=Complexity(time="O(d(n + k))", space="O(n + k)",
                          best="O(d(n + k))", worst="O(d(n + k))"),
    metrics=['array_reads', 'array_writes', 'function_calls'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "After the pass for digit d, the array is sorted by its lowest d+1 digits.",
    ],
    tags=['non-comparison', 'stable', 'integer-keys'],
    annotated=False,
)
