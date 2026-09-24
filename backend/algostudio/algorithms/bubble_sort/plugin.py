"""Bubble Sort -- proves swap lifting from completely un-annotated code."""

from algostudio.plugins.base import AlgorithmPlugin, Complexity, InputField

PLUGIN = AlgorithmPlugin(
    id="bubble_sort",
    name="Bubble Sort",
    category="sorting",
    description=(
        "Repeatedly swap neighbouring items that are out of order until the list is sorted."
    ),
    entry="bubble_sort",
    inputs=[
        InputField("arr", "array", default=[5, 2, 9, 1, 7, 3],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(1)",
                          best="O(n)", worst="O(n^2)"),
    metrics=["comparisons", "swaps", "loop_iterations"],
    invariants=[
        "After pass i, the last i elements are in their final positions.",
    ],
    tags=["comparison-sort", "in-place", "stable", "quadratic"],
    annotated=False,
)
