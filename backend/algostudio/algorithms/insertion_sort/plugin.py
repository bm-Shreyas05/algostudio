"""Insertion Sort -- grow a sorted prefix one element at a time, shifting larger elements right to make room"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="insertion_sort",
    name="Insertion Sort",
    category="sorting",
    description=(
                "Grow a sorted prefix one element at a time, shifting larger elements "
        "right to make room. "
    ),
    entry="insertion_sort",
    inputs=[
        InputField("arr", "array", default=[7, 3, 9, 1, 5, 2],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(1)",
                          best="O(n)", worst="O(n^2)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "arr[0..i-1] is always sorted at the top of each outer iteration.",
    ],
    tags=['comparison-sort', 'in-place', 'stable', 'adaptive'],
    annotated=False,
)
