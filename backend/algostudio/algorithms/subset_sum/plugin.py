"""Subset Sum -- try including and excluding each number, pruning as soon as the remainder goes negative"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="subset_sum",
    name="Subset Sum",
    category="backtracking",
    description=(
                "Try including and excluding each number, pruning as soon as the "
        "remainder goes negative. "
    ),
    entry="subset_sum",
    inputs=[
        InputField("numbers", "array", default=[3, 34, 4, 12, 5, 2],
                   description="Numbers to choose from"),
        InputField("target", "int", default=9,
                   description="Target sum"),
    ],
    complexity=Complexity(time="O(2^n)", space="O(n)",
                          best="O(2^n)", worst="O(2^n)"),
    metrics=['function_calls', 'max_depth', 'pushes', 'pops'],
    viz_hints=[
        VizHint(target="chosen", view="array", weight=0.2),
    ],
    invariants=[
        "sum(chosen) + remaining always equals the original target.",
    ],
    tags=['backtracking', 'recursion', 'pruning'],
    annotated=False,
)
