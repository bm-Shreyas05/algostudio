"""0/1 Knapsack -- fill a table of best-value-for-capacity, deciding for each item whether taking it beats leaving it"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="knapsack",
    name="0/1 Knapsack",
    category="dynamic-programming",
    description=(
                "Fill a table of best-value-for-capacity, deciding for each item "
        "whether taking it beats leaving it. "
    ),
    entry="knapsack",
    inputs=[
        InputField("weights", "array", default=[2, 3, 4, 5],
                   description="Item weights"),
        InputField("values", "array", default=[3, 4, 5, 6],
                   description="Item values"),
        InputField("capacity", "int", default=8,
                   description="Knapsack capacity"),
    ],
    complexity=Complexity(time="O(n * W)", space="O(n * W)",
                          best="O(n * W)", worst="O(n * W)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="table", view="matrix", weight=0.2),
    ],
    invariants=[
        "table[i][c] is the best value using the first i items within capacity c.",
    ],
    tags=['dynamic-programming', 'bottom-up', 'optimisation'],
    annotated=False,
)
