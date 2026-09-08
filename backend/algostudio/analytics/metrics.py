"""Analytics: pure folds over the event stream.

Note what is *not* here: any algorithm-specific counter.  "Comparisons" is a
count of comparison events; "edges relaxed" is a count of ``ALGORITHM_EVENT``s
named ``relax``, which either the user's own ``algo.relax`` call or the relax
lifter produced.  Nothing in this module knows that Dijkstra exists, which is
why adding an algorithm adds its metrics for free.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..core.events import Event, EventType

#: Growth models fitted against measured operation counts.  Advisory: it reports
#: which curve fits the samples, not what the algorithm's complexity "is".
GROWTH_MODELS: dict[str, Any] = {
    "O(1)": lambda n: 1.0,
    "O(log n)": lambda n: math.log2(max(n, 2)),
    "O(n)": lambda n: float(n),
    "O(n log n)": lambda n: n * math.log2(max(n, 2)),
    "O(n^2)": lambda n: float(n) ** 2,
    "O(n^3)": lambda n: float(n) ** 3,
    "O(2^n)": lambda n: float(2 ** min(n, 30)),
}


@dataclass(slots=True)
class Analytics:
    metrics: dict[str, int] = field(default_factory=dict)
    line_hits: dict[int, int] = field(default_factory=dict)
    algorithm_events: dict[str, int] = field(default_factory=dict)
    function_calls: dict[str, int] = field(default_factory=dict)
    max_depth: int = 0
    peak_heap_objects: int = 0
    event_count: int = 0
    duration_ms: float = 0.0
    events_per_category: dict[str, int] = field(default_factory=dict)
    lifted_events: int = 0
    semantic_events: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "line_hits": {str(k): v for k, v in sorted(self.line_hits.items())},
            "algorithm_events": self.algorithm_events,
            "function_calls": self.function_calls,
            "max_depth": self.max_depth,
            "peak_heap_objects": self.peak_heap_objects,
            "event_count": self.event_count,
            "duration_ms": round(self.duration_ms, 3),
            "events_per_category": self.events_per_category,
            "event_origins": {
                "recorded": self.event_count - self.lifted_events - self.semantic_events,
                "lifted": self.lifted_events,
                "semantic": self.semantic_events,
            },
        }


_METRIC_FOR = {
    EventType.LINE_EXECUTED: "statements",
    EventType.VARIABLE_WRITTEN: "variable_writes",
    EventType.VARIABLE_CREATED: "variable_writes",
    EventType.VARIABLE_READ: "variable_reads",
    EventType.SUBSCRIPT_READ: "array_reads",
    EventType.SUBSCRIPT_WRITTEN: "array_writes",
    EventType.SUBSCRIPT_DELETED: "array_writes",
    EventType.ATTRIBUTE_WRITTEN: "attribute_writes",
    EventType.FUNCTION_ENTERED: "function_calls",
    EventType.LOOP_ITERATION: "loop_iterations",
    EventType.CONDITION_EVALUATED: "conditions",
    EventType.BRANCH_TAKEN: "branches",
    EventType.OBJECT_CREATED: "objects_created",
    EventType.OBJECT_MUTATED: "mutations",
    EventType.EXCEPTION_RAISED: "exceptions",
}


def compute(events: Sequence[Event]) -> Analytics:
    a = Analytics(event_count=len(events))
    metrics: Counter[str] = Counter()
    lines: Counter[int] = Counter()
    algo: Counter[str] = Counter()
    calls: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    heap_objects = 0

    for ev in events:
        categories[ev.category] += 1
        metric = _METRIC_FOR.get(ev.type)  # type: ignore[arg-type]
        if metric:
            metrics[metric] += 1
        if ev.loc is not None and ev.type is EventType.LINE_EXECUTED:
            lines[ev.loc.line] += 1
        if ev.type is EventType.EXPRESSION_EVALUATED and ev.payload.get("kind") == "compare":
            metrics["comparisons"] += 1
        if ev.depth > a.max_depth:
            a.max_depth = ev.depth
        if ev.type is EventType.OBJECT_CREATED:
            heap_objects += 1
        elif ev.type is EventType.FUNCTION_ENTERED:
            calls[ev.payload.get("name", "?")] += 1
        elif ev.type is EventType.ALGORITHM_EVENT:
            name = ev.payload.get("name", "?")
            algo[name] += 1
            origin = ev.meta.get("origin")
            if origin == "lifted":
                a.lifted_events += 1
            elif origin == "semantic":
                a.semantic_events += 1
            if name == "metric":
                args = ev.payload.get("args") or {}
                metrics[str(args.get("name", "metric"))] += int(args.get("delta", 1))
        elif ev.type is EventType.PROGRAM_FINISHED:
            a.duration_ms = float(ev.payload.get("duration_ms", 0.0))

    # Semantic operation counts are the algorithm-level metrics students care
    # about; they come from the same open set as everything else.
    plural = {
        "compare": "element_comparisons", "swap": "swaps", "visit": "visits",
        "relax": "relaxations", "enqueue": "enqueues", "dequeue": "dequeues",
        "push": "pushes", "pop": "pops", "merge": "merges",
        "partition": "partitions", "discover": "discoveries",
    }
    for name, label in plural.items():
        if algo.get(name):
            metrics[label] = algo[name]

    a.metrics = dict(metrics)
    a.line_hits = dict(lines)
    a.algorithm_events = dict(algo)
    a.function_calls = dict(calls)
    a.events_per_category = dict(categories)
    a.peak_heap_objects = heap_objects
    return a


def fit_growth(samples: Sequence[tuple[int, float]]) -> dict[str, Any]:
    """Fit measured operation counts against candidate growth curves.

    Least squares on a single scale factor per model, reported with R^2.  This
    is a *description of the samples*, not a proof of complexity, and the API
    labels it as advisory.
    """
    points = [(n, y) for n, y in samples if n > 0 and y > 0]
    if len(points) < 3:
        return {"model": None, "r2": 0.0, "samples": len(points),
                "note": "at least 3 input sizes are needed"}
    mean_y = sum(y for _, y in points) / len(points)
    ss_total = sum((y - mean_y) ** 2 for _, y in points) or 1e-9

    best_model, best_r2, best_scale = None, -1e9, 1.0
    for name, fn in GROWTH_MODELS.items():
        basis = [fn(n) for n, _ in points]
        denom = sum(b * b for b in basis)
        if denom == 0:
            continue
        scale = sum(b * y for b, (_, y) in zip(basis, points)) / denom
        ss_res = sum((y - scale * b) ** 2 for b, (_, y) in zip(basis, points))
        r2 = 1.0 - ss_res / ss_total
        if r2 > best_r2:
            best_model, best_r2, best_scale = name, r2, scale
    return {
        "model": best_model,
        "r2": round(best_r2, 4),
        "scale": round(best_scale, 6),
        "samples": len(points),
        "advisory": True,
    }
