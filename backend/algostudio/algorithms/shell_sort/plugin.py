"""Shell Sort -- insertion sort on progressively smaller gaps, so elements move long distances early and the final gap-1 pass has little left to do"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="shell_sort",
    name="Shell Sort",
    category="sorting",
    description=(
                "Insertion sort on progressively smaller gaps, so elements move long "
        "distances early and the final gap-1 pass has little left to do. "
    ),
    entry="shell_sort",
    inputs=[
        InputField("arr", "array", default=[23, 12, 1, 8, 34, 54, 2, 3],
                   description="Values to sort"),
    ],
    complexity=Complexity(time="O(n^1.3) typical", space="O(1)",
                          best="O(n log n)", worst="O(n^2)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="arr", view="array", weight=0.15),
    ],
    invariants=[
        "After the pass with gap g, every g-th element forms a sorted subsequence.",
    ],
    tags=['comparison-sort', 'in-place', 'unstable'],
    annotated=False,
)
