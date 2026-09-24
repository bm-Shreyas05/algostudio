"""Merge Sort -- proves that divide-and-conquer needs no special support."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="merge_sort",
    name="Merge Sort",
    category="sorting",
    description=(
        "Split the list in half, sort each half recursively, then merge the two sorted halves."
    ),
    entry="merge_sort",
    inputs=[
        InputField("arr", "array", default=[38, 27, 43, 3, 9, 82, 10],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n log n)", space="O(n)",
                          best="O(n log n)", worst="O(n log n)"),
    metrics=["comparisons", "array_writes", "function_calls", "max_depth"],
    viz_hints=[VizHint(target="arr", view="array", weight=0.15)],
    invariants=[
        "Each recursive call returns a sorted list.",
        "Merging two sorted lists of total length k costs at most k-1 comparisons.",
    ],
    tags=["divide-and-conquer", "stable", "recursive"],
    annotated=False,
)
