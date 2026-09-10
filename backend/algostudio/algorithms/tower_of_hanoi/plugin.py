"""Tower of Hanoi -- move a stack of disks between pegs, never putting a larger disk on a smaller one"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="tower_of_hanoi",
    name="Tower of Hanoi",
    category="backtracking",
    description=(
                "Move a stack of disks between pegs, never putting a larger disk on a "
        "smaller one. "
    ),
    entry="hanoi",
    inputs=[
        InputField("disks", "int", default=4,
                   description="Number of disks"),
    ],
    complexity=Complexity(time="O(2^n)", space="O(n)",
                          best="O(2^n)", worst="O(2^n)"),
    metrics=['function_calls', 'max_depth', 'pushes', 'pops'],
    viz_hints=[
        VizHint(target="pegs", view="table", weight=0.2),
    ],
    invariants=[
        "Each peg is always in decreasing order from bottom to top.",
        "Solving n disks takes exactly 2^n - 1 moves.",
    ],
    tags=['recursion', 'divide-and-conquer', 'stack'],
    annotated=False,
)
