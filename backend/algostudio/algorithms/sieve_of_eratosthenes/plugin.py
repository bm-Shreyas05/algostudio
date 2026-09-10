"""Sieve of Eratosthenes -- cross out multiples of each prime in turn; whatever survives is prime"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="sieve_of_eratosthenes",
    name="Sieve of Eratosthenes",
    category="math",
    description=(
                "Cross out multiples of each prime in turn; whatever survives is "
        "prime. "
    ),
    entry="sieve",
    inputs=[
        InputField("limit", "int", default=50,
                   description="Find all primes up to this number"),
    ],
    complexity=Complexity(time="O(n log log n)", space="O(n)",
                          best="O(n log log n)", worst="O(n log log n)"),
    metrics=['array_writes', 'loop_iterations'],
    viz_hints=[
        VizHint(target="flags", view="array", weight=0.2),
    ],
    invariants=[
        "When the outer loop reaches p, every composite below p*p is already crossed out.",
    ],
    tags=['number-theory', 'sieve'],
    annotated=False,
)
