"""Interpolation Search -- guess where the target should be, assuming values are evenly spread, instead of always probing the midpoint"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="interpolation_search",
    name="Interpolation Search",
    category="search",
    description=(
                "Guess where the target should be, assuming values are evenly spread, "
        "instead of always probing the midpoint. "
    ),
    entry="interpolation_search",
    inputs=[
        InputField("arr", "array", default=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
                   description="A sorted list, ideally evenly spaced"),
        InputField("target", "int", default=70,
                   description="Value to find"),
    ],
    complexity=Complexity(time="O(log log n) on uniform data", space="O(1)",
                          best="O(log log n) on uniform data", worst="O(n)"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "arr[low] <= target <= arr[high] holds whenever the loop continues.",
    ],
    tags=['search', 'sorted-input', 'distribution-dependent'],
    annotated=False,
)
