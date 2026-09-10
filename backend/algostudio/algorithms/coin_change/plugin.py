"""Coin Change -- fewest coins that make each amount from 1 upward, building on the answers already found"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="coin_change",
    name="Coin Change",
    category="dynamic-programming",
    description=(
                "Fewest coins that make each amount from 1 upward, building on the "
        "answers already found. "
    ),
    entry="coin_change",
    inputs=[
        InputField("coins", "array", default=[1, 5, 6, 9],
                   description="Coin denominations"),
        InputField("amount", "int", default=11,
                   description="Amount to make"),
    ],
    complexity=Complexity(time="O(amount * coins)", space="O(amount)",
                          best="O(amount * coins)", worst="O(amount * coins)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="best", view="array", weight=0.2),
    ],
    invariants=[
        "best[v] is the minimum number of coins summing to v, or unreachable.",
    ],
    tags=['dynamic-programming', 'bottom-up', 'optimisation'],
    annotated=False,
)
