"""Ternary Search -- split the range into thirds instead of halves"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="ternary_search",
    name="Ternary Search",
    category="search",
    description=(
                "Split the range into thirds instead of halves. More comparisons per "
        "step than binary search, fewer steps — and it loses. "
    ),
    entry="ternary_search",
    inputs=[
        InputField("arr", "array", default=[2, 5, 8, 12, 16, 23, 38, 45, 56, 72, 91],
                   description="A sorted list"),
        InputField("target", "int", default=23,
                   description="Value to find"),
    ],
    complexity=Complexity(time="O(log3 n)", space="O(1)",
                          best="O(log3 n)", worst="O(log3 n)"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "The target, if present, is always within [low, high].",
    ],
    tags=['search', 'sorted-input', 'divide-and-conquer'],
    annotated=False,
)
