"""Kadane's Maximum Subarray -- one pass: at each element, either extend the current run or start a new one from here"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="max_subarray",
    name="Kadane's Maximum Subarray",
    category="dynamic-programming",
    description=(
                "One pass: at each element, either extend the current run or start a "
        "new one from here. "
    ),
    entry="max_subarray",
    inputs=[
        InputField("arr", "array", default=[-2, 1, -3, 4, -1, 2, 1, -5, 4],
                   description="Values"),
    ],
    complexity=Complexity(time="O(n)", space="O(1)",
                          best="O(n)", worst="O(n)"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.2),
    ],
    invariants=[
        "current is the best sum of any run ending at i.",
    ],
    tags=['dynamic-programming', 'linear', 'greedy'],
    annotated=False,
)
