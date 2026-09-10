"""Edit Distance (Levenshtein) -- the fewest insert / delete / substitute operations turning one string into another"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="edit_distance",
    name="Edit Distance (Levenshtein)",
    category="dynamic-programming",
    description=(
                "The fewest insert / delete / substitute operations turning one "
        "string into another. "
    ),
    entry="edit_distance",
    inputs=[
        InputField("first", "string", default='kitten',
                   description="From"),
        InputField("second", "string", default='sitting',
                   description="To"),
    ],
    complexity=Complexity(time="O(n * m)", space="O(n * m)",
                          best="O(n * m)", worst="O(n * m)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="table", view="matrix", weight=0.2),
    ],
    invariants=[
        "table[i][j] is the distance between the first i and first j characters.",
    ],
    tags=['dynamic-programming', 'bottom-up', 'string'],
    annotated=False,
)
