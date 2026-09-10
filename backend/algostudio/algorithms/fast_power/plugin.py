"""Modular Exponentiation -- square-and-multiply: halve the exponent each step instead of multiplying one factor at a time"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField,
)

PLUGIN = AlgorithmPlugin(
    id="fast_power",
    name="Modular Exponentiation",
    category="math",
    description=(
                "Square-and-multiply: halve the exponent each step instead of "
        "multiplying one factor at a time. "
    ),
    entry="fast_power",
    inputs=[
        InputField("base", "int", default=7,
                   description="Base"),
        InputField("exponent", "int", default=45,
                   description="Exponent"),
        InputField("modulus", "int", default=1000,
                   description="Modulus"),
    ],
    complexity=Complexity(time="O(log e)", space="O(1)",
                          best="O(log e)", worst="O(log e)"),
    metrics=['loop_iterations', 'conditions'],
    viz_hints=[

    ],
    invariants=[
        "result * base**exponent (mod m) is constant across the loop.",
    ],
    tags=['number-theory', 'divide-and-conquer', 'cryptography'],
    annotated=False,
)
