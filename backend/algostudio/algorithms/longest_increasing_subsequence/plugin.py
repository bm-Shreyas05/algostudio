"""Longest Increasing Subsequence -- for each position, the best run ending there is one more than the best smaller run before it"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="longest_increasing_subsequence",
    name="Longest Increasing Subsequence",
    category="dynamic-programming",
    description=(
                "For each position, the best run ending there is one more than the "
        "best smaller run before it. "
    ),
    entry="longest_increasing_subsequence",
    inputs=[
        InputField("arr", "array", default=[10, 9, 2, 5, 3, 7, 101, 18],
                   description="Values"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(n)",
                          best="O(n^2)", worst="O(n^2)"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
        VizHint(target="best", view="array", weight=0.2),
    ],
    invariants=[
        "best[i] is the length of the longest increasing run ending at i.",
    ],
    tags=['dynamic-programming', 'bottom-up'],
    annotated=False,
)
