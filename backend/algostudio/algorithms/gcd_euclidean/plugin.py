"""Euclid's GCD -- replace (a, b) with (b, a mod b) until b is zero"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="gcd_euclidean",
    name="Euclid's GCD",
    category="math",
    description=(
                "Replace (a, b) with (b, a mod b) until b is zero. Two thousand years "
        "old and still the fastest thing anyone has. "
    ),
    entry="gcd",
    inputs=[
        InputField("first", "int", default=1071,
                   description="First number"),
        InputField("second", "int", default=462,
                   description="Second number"),
    ],
    complexity=Complexity(time="O(log min(a,b))", space="O(1)",
                          best="O(log min(a,b))", worst="O(log min(a,b))"),
    metrics=['loop_iterations'],
    viz_hints=[

    ],
    invariants=[
        "gcd(a, b) is unchanged by the substitution, which is why it works.",
    ],
    tags=['number-theory', 'iterative'],
    annotated=False,
)
