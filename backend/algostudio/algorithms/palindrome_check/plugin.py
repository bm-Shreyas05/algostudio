"""Palindrome Check -- two pointers walking inward from both ends, ignoring case and punctuation"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="palindrome_check",
    name="Palindrome Check",
    category="string",
    description=(
                "Two pointers walking inward from both ends, ignoring case and "
        "punctuation. "
    ),
    entry="is_palindrome",
    inputs=[
        InputField("text", "string", default='A man, a plan, a canal: Panama',
                   description="Text to test"),
    ],
    complexity=Complexity(time="O(n)", space="O(n)",
                          best="O(n)", worst="O(n)"),
    metrics=['comparisons'],
    viz_hints=[

    ],
    invariants=[
        "Everything outside [low, high] has already been matched.",
    ],
    tags=['two-pointer', 'string'],
    annotated=False,
)
