"""Rabin-Karp -- roll a hash across the text and compare hashes, only checking characters when the hashes agree"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="rabin_karp",
    name="Rabin-Karp",
    category="string",
    description=(
                "Roll a hash across the text and compare hashes, only checking "
        "characters when the hashes agree. "
    ),
    entry="rabin_karp",
    inputs=[
        InputField("text", "string", default='thequickbrownfox',
                   description="Text to search in"),
        InputField("pattern", "string", default='brown',
                   description="Pattern to find"),
    ],
    complexity=Complexity(time="O(n + m) expected", space="O(1)",
                          best="O(n + m) expected", worst="O(nm)"),
    metrics=['comparisons', 'function_calls'],
    viz_hints=[

    ],
    invariants=[
        "window is always the hash of text[i .. i+m-1].",
    ],
    tags=['string-matching', 'hashing', 'rolling-hash'],
    annotated=False,
)
