"""Fibonacci (memoised) -- naive recursion plus a cache"""

from algostudio.plugins.base import (
    AlgorithmPlugin, Complexity, InputField, VizHint,
)

PLUGIN = AlgorithmPlugin(
    id="fibonacci_memo",
    name="Fibonacci (memoised)",
    category="dynamic-programming",
    description=(
                "Naive recursion plus a cache. The cache turns exponential work into "
        "linear, and the call tree shows it. "
    ),
    entry="fibonacci",
    inputs=[
        InputField("n", "int", default=12,
                   description="Which Fibonacci number"),
    ],
    complexity=Complexity(time="O(n)", space="O(n)",
                          best="O(n)", worst="O(n)"),
    metrics=['function_calls', 'max_depth'],
    viz_hints=[
        VizHint(target="memo", view="table", weight=0.2),
    ],
    invariants=[
        "Every value is computed at most once.",
    ],
    tags=['recursion', 'memoisation', 'top-down'],
    annotated=False,
)
