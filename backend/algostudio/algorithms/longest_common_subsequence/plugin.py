"""Longest Common Subsequence -- fill a table of match lengths, then walk backwards through it to recover the actual subsequence"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="longest_common_subsequence",
    name="Longest Common Subsequence",
    category="dynamic-programming",
    description=(
                "Fill a table of match lengths, then walk backwards through it to "
        "recover the actual subsequence. "
    ),
    entry="lcs",
    inputs=[
        InputField("first", "string", default='AGGTAB',
                   description="First sequence"),
        InputField("second", "string", default='GXTXAYB',
                   description="Second sequence"),
    ],
    complexity=Complexity(time="O(n * m)", space="O(n * m)",
                          best="O(n * m)", worst="O(n * m)"),
    metrics=['comparisons', 'array_writes'],
    viz_hints=[
        VizHint(target="table", view="matrix", weight=0.2),
    ],
    invariants=[
        "table[i][j] is the LCS length of the first i and first j characters.",
    ],
    tags=['dynamic-programming', 'bottom-up', 'string', 'traceback'],
    annotated=False,
)
