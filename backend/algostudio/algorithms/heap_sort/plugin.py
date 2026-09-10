"""Heap Sort -- build a max-heap in place, then repeatedly swap the root to the end and sift down"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="heap_sort",
    name="Heap Sort",
    category="sorting",
    description=(
                "Build a max-heap in place, then repeatedly swap the root to the end "
        "and sift down. The heap detector picks up the array's structure. "
    ),
    entry="heap_sort",
    inputs=[
        InputField("arr", "array", default=[5, 13, 2, 25, 7, 17, 20, 8],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n log n)", space="O(1)",
                          best="O(n log n)", worst="O(n log n)"),
    metrics=['comparisons', 'swaps', 'function_calls'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "arr[0..size-1] satisfies the max-heap property before each extraction.",
    ],
    tags=['comparison-sort', 'in-place', 'unstable', 'heap'],
    annotated=False,
)
