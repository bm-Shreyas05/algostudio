"""Rod Cutting -- best revenue from cutting a rod, given a price for each length"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="rod_cutting",
    name="Rod Cutting",
    category="dynamic-programming",
    description=(
                "Best revenue from cutting a rod, given a price for each length. "
    ),
    entry="rod_cutting",
    inputs=[
        InputField("prices", "array", default=[1, 5, 8, 9, 10, 17, 17, 20],
                   description="Price for length 1, 2, 3..."),
        InputField("length", "int", default=8,
                   description="Rod length"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(n)",
                          best="O(n^2)", worst="O(n^2)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="best", view="array", weight=0.2),
    ],
    invariants=[
        "best[s] is the maximum revenue obtainable from a rod of length s.",
    ],
    tags=['dynamic-programming', 'bottom-up', 'optimisation'],
    annotated=False,
)
