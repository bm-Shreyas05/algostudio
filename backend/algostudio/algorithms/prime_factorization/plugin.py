"""Prime Factorization -- divide out the smallest factor repeatedly"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="prime_factorization",
    name="Prime Factorization",
    category="math",
    description=(
                "Divide out the smallest factor repeatedly. Stopping at sqrt(n) is "
        "what makes it fast. "
    ),
    entry="prime_factors",
    inputs=[
        InputField("number", "int", default=360,
                   description="Number to factorise"),
    ],
    complexity=Complexity(time="O(sqrt(n))", space="O(log n)",
                          best="O(sqrt(n))", worst="O(sqrt(n))"),
    metrics=['loop_iterations', 'conditions'],
    viz_hints=[
        VizHint(target="factors", view="array", weight=0.15),
    ],
    invariants=[
        "number * product(factors) equals the original input at every step.",
    ],
    tags=['number-theory', 'trial-division'],
    annotated=False,
)
