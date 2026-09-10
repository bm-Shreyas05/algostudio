"""Jump Search -- jump forward in blocks of sqrt(n), then walk backwards through the block that must contain the target"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="jump_search",
    name="Jump Search",
    category="search",
    description=(
                "Jump forward in blocks of sqrt(n), then walk backwards through the "
        "block that must contain the target. "
    ),
    entry="jump_search",
    inputs=[
        InputField("arr", "array", default=[1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25],
                   description="A sorted list"),
        InputField("target", "int", default=17,
                   description="Value to find"),
    ],
    complexity=Complexity(time="O(sqrt(n))", space="O(1)",
                          best="O(1)", worst="O(sqrt(n))"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "The target, if present, always lies in [prev, current).",
    ],
    tags=['search', 'sorted-input'],
    annotated=False,
)
