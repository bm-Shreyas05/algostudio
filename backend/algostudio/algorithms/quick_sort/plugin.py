"""Quick Sort -- partition around a pivot, then sort each side"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="quick_sort",
    name="Quick Sort",
    category="sorting",
    description=(
                "Partition around a pivot, then sort each side. In-place, and the "
        "swaps in the partition step are recovered by the swap lifter. "
    ),
    entry="quick_sort",
    inputs=[
        InputField("arr", "array", default=[9, 4, 7, 1, 8, 2, 6],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n log n)", space="O(log n)",
                          best="O(n log n)", worst="O(n^2)"),
    metrics=['comparisons', 'swaps', 'function_calls'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "After partition, everything left of the pivot is <= it and everything right of it is >= it.",
    ],
    tags=['divide-and-conquer', 'in-place', 'unstable'],
    annotated=False,
)
