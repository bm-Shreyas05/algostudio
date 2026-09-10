"""Bracket Matching -- push opening brackets, pop on closing ones, and check they pair up"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="bracket_matching",
    name="Bracket Matching",
    category="data-structure",
    description=(
                "Push opening brackets, pop on closing ones, and check they pair up. "
        "The canonical use for a stack. "
    ),
    entry="bracket_matcher",
    inputs=[
        InputField("text", "string", default='{[()()]}([])',
                   description="Text to check"),
    ],
    complexity=Complexity(time="O(n)", space="O(n)",
                          best="O(n)", worst="O(n)"),
    metrics=['pushes', 'pops', 'comparisons'],
    viz_hints=[
        VizHint(target="stack", view="stack", weight=0.2),
    ],
    invariants=[
        "The stack holds exactly the brackets opened and not yet closed.",
    ],
    tags=['stack', 'parsing', 'linear'],
    annotated=False,
)
