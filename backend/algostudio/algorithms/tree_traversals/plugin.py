"""Tree Traversals -- pre-order, in-order and post-order over the same tree"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="tree_traversals",
    name="Tree Traversals",
    category="tree",
    description=(
                "Pre-order, in-order and post-order over the same tree. Only the "
        "position of one line differs. "
    ),
    entry="traversals",
    inputs=[
        InputField("values", "array", default=[8, 3, 10, 1, 6, 14, 4, 7, 13],
                   description="Values to insert"),
    ],
    complexity=Complexity(time="O(n)", space="O(h)",
                          best="O(n)", worst="O(n)"),
    metrics=['function_calls', 'max_depth'],
    viz_hints=[

    ],
    invariants=[
        "Each traversal visits every node exactly once.",
    ],
    tags=['tree', 'recursion', 'traversal'],
    annotated=False,
)
