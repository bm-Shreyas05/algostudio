"""N-Queens -- place queens row by row, backing out the moment two threaten each other"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="n_queens",
    name="N-Queens",
    category="backtracking",
    description=(
                "Place queens row by row, backing out the moment two threaten each "
        "other. "
    ),
    entry="n_queens",
    inputs=[
        InputField("n", "int", default=5,
                   description="Board size"),
    ],
    complexity=Complexity(time="O(n!)", space="O(n)",
                          best="O(n!)", worst="O(n!)"),
    metrics=['function_calls', 'comparisons', 'max_depth'],
    viz_hints=[
        VizHint(target="board", view="array", weight=0.2),
    ],
    invariants=[
        "board[r] is the column of the queen in row r, or -1 for none.",
        "No two placed queens ever share a column or diagonal.",
    ],
    tags=['backtracking', 'recursion', 'constraint'],
    annotated=False,
)
