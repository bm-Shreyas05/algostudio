"""Linear Search -- scan from the start until the target is found"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="linear_search",
    name="Linear Search",
    category="search",
    description=(
                "Scan from the start until the target is found. The baseline every "
        "other search is measured against. "
    ),
    entry="linear_search",
    inputs=[
        InputField("arr", "array", default=[14, 3, 27, 8, 41, 6, 19],
                   description="Values to search"),
        InputField("target", "int", default=41,
                   description="Value to find"),
    ],
    complexity=Complexity(time="O(n)", space="O(1)",
                          best="O(1)", worst="O(n)"),
    metrics=['comparisons', 'array_reads'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "If the target is at index k, exactly k+1 elements are examined.",
    ],
    tags=['search', 'unsorted-input'],
    annotated=False,
)
