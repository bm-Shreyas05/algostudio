"""Anagram Check -- tally the letters of one word, then spend them against the other"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="anagram_check",
    name="Anagram Check",
    category="string",
    description=(
                "Tally the letters of one word, then spend them against the other. An "
        "empty tally at the end means they match. "
    ),
    entry="is_anagram",
    inputs=[
        InputField("first", "string", default='listen',
                   description="First word"),
        InputField("second", "string", default='silent',
                   description="Second word"),
    ],
    complexity=Complexity(time="O(n)", space="O(k)",
                          best="O(n)", worst="O(n)"),
    metrics=['mutations'],
    viz_hints=[
        VizHint(target="counts", view="table", weight=0.15),
    ],
    invariants=[
        "counts holds the unmatched letters of `first` at every step.",
    ],
    tags=['hashing', 'counting', 'string'],
    annotated=False,
)
