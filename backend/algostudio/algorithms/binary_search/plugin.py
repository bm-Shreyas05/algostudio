"""Binary Search -- proves pointer/region annotation and branch visualization."""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="binary_search",
    name="Binary Search",
    category="search",
    description=(
        "Find a target in a sorted array by repeatedly halving the search "
        "window. Annotated with algo.pointer/algo.region so the array view "
        "shows low, mid and high explicitly."
    ),
    entry="binary_search",
    inputs=[
        InputField("arr", "array", default=[1, 3, 5, 7, 9, 11, 13, 15, 17, 19],
                   description="A sorted list of numbers"),
        InputField("target", "int", default=13, description="Value to find"),
    ],
    complexity=Complexity(time="O(log n)", space="O(1)",
                          best="O(1)", worst="O(log n)"),
    metrics=["comparisons", "loop_iterations"],
    viz_hints=[VizHint(target="arr", view="array", weight=0.15)],
    invariants=[
        "If the target is present, its index is always within [low, high].",
        "The search window at least halves on every iteration.",
    ],
    tags=["divide-and-conquer", "sorted-input", "iterative"],
    annotated=True,
)
