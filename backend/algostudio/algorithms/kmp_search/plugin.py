"""Knuth-Morris-Pratt -- substring search that never re-examines a character, using a prefix table to decide how far to slide the pattern"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="kmp_search",
    name="Knuth-Morris-Pratt",
    category="string",
    description=(
                "Substring search that never re-examines a character, using a prefix "
        "table to decide how far to slide the pattern. "
    ),
    entry="kmp_search",
    inputs=[
        InputField("text", "string", default='abxabcabcaby',
                   description="Text to search in"),
        InputField("pattern", "string", default='abcaby',
                   description="Pattern to find"),
    ],
    complexity=Complexity(time="O(n + m)", space="O(m)",
                          best="O(n + m)", worst="O(n + m)"),
    metrics=['comparisons', 'array_reads', 'function_calls'],
    viz_hints=[
        VizHint(target="table", view="array", weight=0.15),
    ],
    invariants=[
        "table[i] is the length of the longest proper prefix of pattern[0..i] that is also a suffix of it.",
    ],
    tags=['string-matching', 'linear', 'preprocessing'],
    annotated=False,
)
