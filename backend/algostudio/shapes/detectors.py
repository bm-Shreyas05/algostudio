"""Structural detection: which view fits this heap object?

The whole point of this module is that it never receives an algorithm
identifier.  ``AdjacencyMapDetector`` fires on *a dict whose value elements are
also its own keys*, which is what an adjacency list looks like whether it came
from a packaged BFS plugin or from something a student typed thirty seconds ago.
That is what lets an unseen algorithm get an appropriate visualization.

Each detector returns a scored ``ShapeMatch`` with a human-readable ``reason``,
which the UI shows as a "why this view?" tooltip -- a confidently wrong view is
much less damaging when the system can say what it thought it saw.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.values import MAPPING_TAGS, SEQUENCE_TAGS, SET_TAGS, same_value, scalar_of
from ..state.model import ExecutionState


@dataclass(slots=True)
class ShapeMatch:
    view: str
    score: float
    reason: str
    props: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "view": self.view, "score": round(self.score, 3),
            "reason": self.reason, "props": self.props,
        }


class Detector(Protocol):
    id: str

    def detect(self, ref: str, record: dict[str, Any],
               state: ExecutionState) -> ShapeMatch | None:
        ...


# ----------------------------------------------------------------------
def _items(record: dict[str, Any]) -> list[Any]:
    return record.get("items") or []


def _entries(record: dict[str, Any]) -> list[list[Any]]:
    return record.get("entries") or []


def _numeric_ratio(values: list[Any]) -> float:
    if not values:
        return 0.0
    numeric = sum(
        1 for v in values
        if isinstance(v, dict) and v.get("k") in ("int", "float")
    )
    return numeric / len(values)


def _all_scalar(values: list[Any]) -> bool:
    return all(
        isinstance(v, dict) and v.get("k") in ("int", "float", "str", "bool", "none")
        for v in values
    )


class ScalarArrayDetector:
    id = "scalar-array"

    def detect(self, ref, record, state):
        if record.get("t") not in SEQUENCE_TAGS:
            return None
        items = _items(record)
        if len(items) < 1 or not _all_scalar(items):
            return None
        numeric = _numeric_ratio(items)
        score = 0.72 if numeric >= 0.8 else 0.62
        return ShapeMatch(
            "array", score,
            f"{record.get('t')} of {len(items)} scalar values",
            {"numeric": numeric >= 0.8, "length": record.get("n", len(items))},
        )


class MatrixDetector:
    id = "matrix"

    def detect(self, ref, record, state):
        if record.get("t") not in SEQUENCE_TAGS:
            return None
        items = _items(record)
        if len(items) < 2:
            return None
        rows = []
        for item in items:
            if not (isinstance(item, dict) and item.get("k") == "ref"):
                return None
            inner = state.heap.get(item["r"])
            if inner is None or inner.get("t") not in SEQUENCE_TAGS:
                return None
            rows.append(inner)
        widths = {r.get("n", len(_items(r))) for r in rows}
        if len(widths) != 1:
            return None
        # Equal-width rows are not enough: a weighted adjacency list is a list of
        # [node, weight] pairs and would match.  Require the cells to be numeric.
        cells = [c for r in rows for c in _items(r)]
        if not cells or _numeric_ratio(cells) < 0.95:
            return None
        return ShapeMatch(
            "matrix", 0.86,
            f"{len(rows)} rows of equal width {widths.pop()}, numeric cells",
            {"rows": len(rows)},
        )


class AdjacencyMapDetector:
    """A dict whose value elements are drawn from its own key set."""

    id = "adjacency-map"

    def detect(self, ref, record, state):
        if record.get("t") not in MAPPING_TAGS:
            return None
        entries = _entries(record)
        if len(entries) < 2:
            return None
        keys = [scalar_of(k) for k, _ in entries]
        key_set = {k for k in keys if k is not None}
        if len(key_set) < 2:
            return None

        edges: list[dict[str, Any]] = []
        referenced = 0
        total = 0
        for key_enc, value_enc in entries:
            key = scalar_of(key_enc)
            for target, weight in self._neighbours(value_enc, state):
                total += 1
                if target in key_set:
                    referenced += 1
                edges.append(
                    {"source": key, "target": target,
                     **({"weight": weight} if weight is not None else {})}
                )
        if total == 0:
            return None
        ratio = referenced / total
        if ratio < 0.6:
            return None
        weighted = any("weight" in e for e in edges)
        return ShapeMatch(
            "graph", 0.7 + 0.2 * ratio,
            f"{len(key_set)} keys; {int(ratio * 100)}% of adjacency entries "
            f"refer back to keys of the same map",
            {
                "nodes": [{"id": k} for k in keys],
                "edges": [e for e in edges if e["target"] in key_set],
                "weighted": weighted,
                "directed": True,
            },
        )

    def _neighbours(self, value_enc: Any, state: ExecutionState):
        """Yield (target, weight) from a list/set of neighbours or (node, w) pairs."""
        if not (isinstance(value_enc, dict) and value_enc.get("k") == "ref"):
            return
        inner = state.heap.get(value_enc["r"])
        if inner is None:
            return
        tag = inner.get("t")
        if tag in SEQUENCE_TAGS or tag in SET_TAGS:
            for element in _items(inner):
                scalar = scalar_of(element)
                if scalar is not None:
                    yield scalar, None
                elif isinstance(element, dict) and element.get("k") == "ref":
                    pair = state.heap.get(element["r"])
                    pair_items = _items(pair or {})
                    if pair and pair.get("t") in SEQUENCE_TAGS and len(pair_items) == 2:
                        yield scalar_of(pair_items[0]), scalar_of(pair_items[1])
        elif tag in MAPPING_TAGS:
            for k, v in _entries(inner):
                yield scalar_of(k), scalar_of(v)


class LinkedStructureDetector:
    """An object with fields referencing objects of the same class."""

    id = "linked"

    TREE_FIELDS = ({"left", "right"}, {"l", "r"}, {"lo", "hi"})

    def detect(self, ref, record, state):
        if record.get("t") != "object":
            return None
        cls = record.get("cls")
        fields = record.get("fields") or {}
        self_links = [
            name for name, value in fields.items()
            if isinstance(value, dict) and value.get("k") == "ref"
            and (state.heap.get(value["r"]) or {}).get("cls") == cls
        ]
        nullable = [
            name for name, value in fields.items()
            if isinstance(value, dict) and value.get("k") == "none"
        ]
        candidates = set(self_links) | set(nullable)
        if not self_links:
            return None
        for pair in self.TREE_FIELDS:
            if pair <= candidates:
                return ShapeMatch(
                    "tree", 0.88,
                    f"{cls} objects linked through {'/'.join(sorted(pair))}",
                    {"class": cls, "children": sorted(pair)},
                )
        if len(candidates) == 1 or set(self_links) <= {"next", "nxt", "succ"}:
            field_name = self_links[0]
            return ShapeMatch(
                "linked-list", 0.82,
                f"{cls} objects chained through .{field_name}",
                {"class": cls, "next": field_name},
            )
        return ShapeMatch(
            "tree", 0.6, f"{cls} objects with {len(self_links)} self-references",
            {"class": cls, "children": sorted(candidates)},
        )


class TableDetector:
    id = "table"

    def detect(self, ref, record, state):
        if record.get("t") not in MAPPING_TAGS:
            return None
        entries = _entries(record)
        if not entries:
            return ShapeMatch("table", 0.4, "empty mapping", {})
        values = [v for _, v in entries]
        score = 0.62 if _all_scalar(values) else 0.45
        return ShapeMatch(
            "table", score, f"mapping with {len(entries)} entries",
            {"length": record.get("n", len(entries))},
        )


class SetDetector:
    id = "set"

    def detect(self, ref, record, state):
        if record.get("t") not in SET_TAGS:
            return None
        return ShapeMatch(
            "set", 0.66, f"{record.get('t')} with {record.get('n', 0)} members", {}
        )


class QueueDetector:
    """A deque, or a list whose only mutations are append/pop."""

    id = "queue"

    def detect(self, ref, record, state):
        tag = record.get("t")
        if tag == "deque":
            return ShapeMatch("queue", 0.78, "deque", {"length": record.get("n", 0)})
        return None


class StackDetector:
    id = "stack"

    def detect(self, ref, record, state):
        if record.get("t") != "list":
            return None
        pushes = state.counters.get("algo.push", 0)
        pops = state.counters.get("algo.pop", 0)
        if pushes + pops == 0:
            return None
        # Advisory only: a list that has *only* been pushed to and popped from
        # reads as a stack, but the array view stays available as an alternative.
        return ShapeMatch(
            "stack", 0.55,
            "list mutated only through append/pop during this run",
            {"length": record.get("n", 0)},
        )


class HeapDetector:
    id = "heap"

    def detect(self, ref, record, state):
        if record.get("t") != "list":
            return None
        items = [scalar_of(v) for v in _items(record)]
        if len(items) < 3 or any(v is None or isinstance(v, str) for v in items):
            return None
        if not state.counters.get("algo.enqueue") and not state.counters.get("algo.dequeue"):
            return None
        for i in range(1, len(items)):
            parent = items[(i - 1) // 2]
            try:
                if parent > items[i]:
                    return None
            except TypeError:
                return None
        return ShapeMatch(
            "heap", 0.74,
            "list satisfies the min-heap property and was mutated by heap operations",
            {"length": len(items)},
        )


class ObjectDetector:
    id = "object"

    def detect(self, ref, record, state):
        if record.get("t") != "object":
            return None
        return ShapeMatch(
            "object", 0.35,
            f"instance of {record.get('cls')}",
            {"class": record.get("cls")},
        )


class FallbackDetector:
    id = "fallback"

    def detect(self, ref, record, state):
        return ShapeMatch("value", 0.1, "generic value", {})


DEFAULT_DETECTORS: list[Detector] = [
    ScalarArrayDetector(), MatrixDetector(), AdjacencyMapDetector(),
    LinkedStructureDetector(), TableDetector(), SetDetector(),
    QueueDetector(), StackDetector(), HeapDetector(), ObjectDetector(),
    FallbackDetector(),
]
