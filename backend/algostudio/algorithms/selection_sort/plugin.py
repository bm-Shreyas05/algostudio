"""Selection Sort -- repeatedly find the smallest remaining element and swap it into place"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="selection_sort",
    name="Selection Sort",
    category="sorting",
    description=(
                "Repeatedly find the smallest remaining element and swap it into "
        "place. Always the same number of comparisons, whatever the input. "
    ),
    entry="selection_sort",
    inputs=[
        InputField("arr", "array", default=[6, 2, 8, 4, 1, 9],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n^2)", space="O(1)",
                          best="O(n^2)", worst="O(n^2)"),
    metrics=['comparisons', 'swaps'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "After pass i, arr[0..i] holds the i+1 smallest values in order.",
    ],
    tags=['comparison-sort', 'in-place', 'unstable'],
    annotated=False,
)
