"""Binary Search Tree -- insert a sequence of values, then search for one and read the tree back in order"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="bst_operations",
    name="Binary Search Tree",
    category="tree",
    description=(
                "Insert a sequence of values, then search for one and read the tree "
        "back in order. "
    ),
    entry="bst_demo",
    inputs=[
        InputField("values", "array", default=[50, 30, 70, 20, 40, 60, 80],
                   description="Values to insert"),
        InputField("target", "int", default=60,
                   description="Value to search for"),
    ],
    complexity=Complexity(time="O(h) per operation", space="O(n)",
                          best="O(log n)", worst="O(n)"),
    metrics=['comparisons', 'function_calls', 'max_depth'],
    viz_hints=[

    ],
    invariants=[
        "Everything in a left subtree is smaller than its root; everything right is larger.",
        "An in-order walk of a BST is always sorted.",
    ],
    tags=['tree', 'recursion', 'ordered'],
    annotated=False,
)
