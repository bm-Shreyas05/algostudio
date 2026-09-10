"""Permutations -- generate every ordering by swapping each candidate into position and recursing on the rest"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="permutations",
    name="Permutations",
    category="backtracking",
    description=(
                "Generate every ordering by swapping each candidate into position and "
        "recursing on the rest. "
    ),
    entry="permutations",
    inputs=[
        InputField("items", "array", default=[1, 2, 3, 4],
                   description="Items to permute"),
    ],
    complexity=Complexity(time="O(n * n!)", space="O(n)",
                          best="O(n * n!)", worst="O(n * n!)"),
    metrics=['swaps', 'function_calls', 'max_depth'],
    viz_hints=[
        VizHint(target="items", view="array", weight=0.2),
    ],
    invariants=[
        "items[0..start-1] is a fixed prefix; everything after it is still being permuted.",
    ],
    tags=['backtracking', 'recursion', 'combinatorics'],
    annotated=False,
)
