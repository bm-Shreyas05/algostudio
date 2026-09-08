"""Algorithm comparison on identical input.

The only interesting design point: both algorithms must receive the *same*
generated input, and the input is seeded, so a comparison is reproducible.
Metrics come from the ordinary analytics fold, so a newly added algorithm is
comparable the moment it exists -- no per-algorithm benchmark code.
"""

from __future__ import annotations

from typing import Any

from ..analytics.metrics import fit_growth
from ..inputs import generators
from ..plugins.registry import REGISTRY as PLUGINS
from .execution_service import ExecutionService

COMPARISON_METRICS = (
    "statements", "comparisons", "element_comparisons", "swaps",
    "array_reads", "array_writes", "function_calls", "loop_iterations",
    "visits", "relaxations", "enqueues", "dequeues", "objects_created",
)


class BenchmarkService:
    def __init__(self, executions: ExecutionService) -> None:
        self.executions = executions

    def compare(self, algorithm_ids: list[str], input_spec: dict[str, Any],
                sizes: list[int] | None = None,
                granularity: str = "minimal") -> dict[str, Any]:
        """Run each algorithm over each input size and tabulate the results.

        Defaults to ``minimal`` granularity: a benchmark measures the
        algorithm's operation counts, and paying for expression-level events
        that nobody will look at only shrinks the input sizes we can afford.
        """
        sizes = sizes or [int(input_spec.get("size", 20))]
        runs: list[dict[str, Any]] = []
        for size in sizes:
            spec = {**input_spec, "size": size}
            if spec.get("kind") in ("graph", "weighted_graph"):
                spec["nodes"] = size
            generated = generators.generate(**spec)
            for algorithm_id in algorithm_ids:
                runs.append(self._run_one(algorithm_id, generated, size, granularity))

        table = self._table(runs)
        return {
            "input_spec": input_spec,
            "sizes": sizes,
            "algorithms": algorithm_ids,
            "runs": runs,
            "table": table,
            "growth": self._growth(runs, algorithm_ids),
        }

    # ------------------------------------------------------------------
    def _run_one(self, algorithm_id: str, generated: dict[str, Any],
                 size: int, granularity: str) -> dict[str, Any]:
        plugin = PLUGINS.get(algorithm_id)
        primary = plugin.inputs[0].name if plugin.inputs else None
        inputs: dict[str, Any] = {}
        if primary:
            inputs[primary] = generated["value"]
        for field in plugin.inputs[1:]:
            inputs[field.name] = self._default_for(field, generated["value"])

        result = self.executions.run_algorithm(
            algorithm_id, inputs, granularity=granularity
        )
        analytics = self.executions.analytics(result.execution_id)
        metrics = analytics.get("metrics", {})
        return {
            "algorithm_id": algorithm_id,
            "algorithm": plugin.name,
            "execution_id": result.execution_id,
            "size": size,
            "status": result.status,
            "wall_ms": round(result.wall_ms, 2),
            "event_count": result.event_count,
            "max_depth": analytics.get("max_depth", 0),
            "metrics": {k: metrics.get(k, 0) for k in COMPARISON_METRICS
                        if k in metrics},
            "complexity": plugin.complexity.to_dict() if plugin.complexity else None,
        }

    def _default_for(self, field: Any, value: Any) -> Any:
        """Pick a sensible secondary input, e.g. a source node that exists."""
        if field.kind == "node" and isinstance(value, dict) and value:
            return next(iter(value))
        if field.kind == "int" and isinstance(value, list) and value:
            return value[len(value) // 2]
        return field.default

    def _table(self, runs: list[dict[str, Any]]) -> dict[str, Any]:
        columns = sorted({k for r in runs for k in r["metrics"]})
        return {
            "columns": ["algorithm", "size", "wall_ms", "event_count", *columns],
            "rows": [
                [r["algorithm"], r["size"], r["wall_ms"], r["event_count"],
                 *[r["metrics"].get(c, 0) for c in columns]]
                for r in runs
            ],
        }

    def _growth(self, runs: list[dict[str, Any]],
                algorithm_ids: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for algorithm_id in algorithm_ids:
            samples = [
                (r["size"], float(r["metrics"].get("statements", r["event_count"])))
                for r in runs if r["algorithm_id"] == algorithm_id
            ]
            out[algorithm_id] = fit_growth(samples)
        return out
