"""Linked List Reversal -- reverse a singly linked list in place by re-pointing each node's next as you walk"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="linked_list_reversal",
    name="Linked List Reversal",
    category="data-structure",
    description=(
                "Reverse a singly linked list in place by re-pointing each node's "
        "next as you walk. "
    ),
    entry="reverse_list",
    inputs=[
        InputField("values", "array", default=[1, 2, 3, 4, 5],
                   description="Values, head first"),
    ],
    complexity=Complexity(time="O(n)", space="O(1)",
                          best="O(n)", worst="O(n)"),
    metrics=['attribute_writes', 'loop_iterations'],
    viz_hints=[

    ],
    invariants=[
        "previous heads the already-reversed prefix; current heads the rest.",
    ],
    tags=['data-structure', 'pointers', 'in-place'],
    annotated=False,
)
