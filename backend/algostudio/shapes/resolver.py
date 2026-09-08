"""View resolution: turn detector matches into an ordered layout plan.

Two rules keep the project's central claim intact:

1. **Detection is sticky.**  Views are resolved against the *final* heap and
   applied to every step.  Re-detecting per step would make an empty
   ``visited = set()`` render as nothing until it happens to fill, and the
   canvas would flicker between view types as data arrives.

2. **A plugin hint can bias, never create.**  ``Sum(hint.weight)`` is capped and
   applies only to views a detector already proposed with a non-zero score.
   That is the mechanical reason a student's own Dijkstra gets the same graph
   view as the packaged one: the graph view was chosen by looking at the data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..state.model import ExecutionState
from .detectors import DEFAULT_DETECTORS, Detector, ShapeMatch

MAX_HINT_WEIGHT = 0.3
DEFAULT_PRIMARY = 3


@dataclass(slots=True)
class ViewDescriptor:
    ref: str
    view: str
    score: float
    reason: str
    name: str = ""
    kind: str = ""
    props: dict[str, Any] = field(default_factory=dict)
    alternatives: list[dict[str, Any]] = field(default_factory=list)
    primary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref, "view": self.view, "score": round(self.score, 3),
            "reason": self.reason, "name": self.name, "kind": self.kind,
            "props": self.props, "alternatives": self.alternatives,
            "primary": self.primary,
        }


class ViewResolver:
    def __init__(self, detectors: Iterable[Detector] | None = None) -> None:
        self.detectors = list(detectors or DEFAULT_DETECTORS)

    def resolve(
        self,
        state: ExecutionState,
        hints: Iterable[dict[str, Any]] = (),
        pins: dict[str, str] | None = None,
        primary: int = DEFAULT_PRIMARY,
    ) -> list[ViewDescriptor]:
        pins = pins or {}
        names = state.ref_names()
        hint_list = list(hints)
        annotated = {a.target_ref for a in state.live_annotations() if a.target_ref}

        plans: list[ViewDescriptor] = []
        for ref, record in state.heap.items():
            matches = [
                m for m in (d.detect(ref, record, state) for d in self.detectors)
                if m is not None
            ]
            if not matches:
                continue
            best_by_view: dict[str, ShapeMatch] = {}
            for match in matches:
                current = best_by_view.get(match.view)
                if current is None or match.score > current.score:
                    best_by_view[match.view] = match

            name = names.get(ref, "")
            scored: list[tuple[float, ShapeMatch]] = []
            for view, match in best_by_view.items():
                score = match.score
                score += self._hint_bonus(hint_list, view, name)
                if pins.get(ref) == view:
                    score += 0.5
                if ref in annotated:
                    score += 0.15
                if not name:
                    score -= 0.3        # unreferenced by any live binding
                scored.append((score, match))
            scored.sort(key=lambda pair: pair[0], reverse=True)

            top_score, top = scored[0]
            plans.append(
                ViewDescriptor(
                    ref=ref,
                    view=top.view,
                    score=top_score,
                    reason=top.reason,
                    name=name,
                    kind=record.get("t", ""),
                    props=top.props,
                    alternatives=[
                        {"view": m.view, "score": round(s, 3), "reason": m.reason}
                        for s, m in scored[1:4]
                    ],
                )
            )

        plans.sort(key=lambda p: (p.score, p.name != "", p.ref), reverse=True)
        for i, plan in enumerate(plans):
            plan.primary = i < primary
        return plans

    def _hint_bonus(self, hints: list[dict[str, Any]], view: str, name: str) -> float:
        total = 0.0
        for hint in hints:
            if hint.get("view") != view:
                continue
            target = hint.get("target")
            if target and name and target != name:
                continue
            total += float(hint.get("weight", 0.1))
        return min(total, MAX_HINT_WEIGHT)
