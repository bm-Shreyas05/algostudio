"""Runs the lifters over a recorded event stream."""

from __future__ import annotations

from typing import Sequence

from ..core.events import Event, EventType
from .base import LiftContext, Lifter
from .detectors import DEFAULT_LIFTERS


class LifterPipeline:
    def __init__(self, lifters: Sequence[Lifter] | None = None) -> None:
        self.lifters: list[Lifter] = list(
            lifters if lifters is not None else [cls() for cls in DEFAULT_LIFTERS]
        )

    def process(self, events: Sequence[Event]) -> list[Event]:
        """Return the stream with lifted events interleaved.

        A lifted event is inserted immediately after the raw event that
        triggered it and inherits its frame, depth and location, so the timeline
        can collapse ``SWAP`` together with the two writes that produced it.
        Ids are renumbered afterwards by ``timeline.normalize_ids``.
        """
        ctx = LiftContext()
        for lifter in self.lifters:
            lifter.reset()
        out: list[Event] = []
        for ev in events:
            ctx.observe(ev)
            out.append(ev)
            for lifter in self.lifters:
                try:
                    produced = lifter.feed(ev, ctx)
                except Exception:
                    # A misbehaving lifter must never lose the recording: the
                    # raw stream is the source of truth, lifting is enrichment.
                    produced = []
                if produced:
                    out.extend(produced)
        return _drop_redundant(out)

    @property
    def ids(self) -> list[str]:
        return [l.id for l in self.lifters]


#: How far apart a declared and an inferred event may be and still describe the
#: same operation.  ``visited.add(u)`` and ``algo.visit(u)`` are adjacent lines.
DUPLICATE_SPAN = 12


def _drop_redundant(events: list[Event]) -> list[Event]:
    """Remove lifted events that duplicate one the code already declared.

    A lifter is a streaming state machine, so it cannot know that two lines
    later the program will call ``algo.visit`` for the node it just inferred a
    visit for.  Dijkstra does exactly that -- ``visited.add(u)`` then
    ``algo.visit(u)`` -- which produced two events per visit, two annotations on
    the same node, and a "visits" metric of 12 for a six-node graph.

    Declared semantics win: the author said what they meant.
    """
    declared: dict[tuple[str, str], list[int]] = {}
    for index, ev in enumerate(events):
        if ev.type is not EventType.ALGORITHM_EVENT:
            continue
        if ev.meta.get("origin") != "semantic":
            continue
        key = (ev.payload.get("name", ""), _subject(ev))
        declared.setdefault(key, []).append(index)

    if not declared:
        return events

    out: list[Event] = []
    for index, ev in enumerate(events):
        if (
            ev.type is EventType.ALGORITHM_EVENT
            and ev.meta.get("origin") == "lifted"
        ):
            key = (ev.payload.get("name", ""), _subject(ev))
            nearby = declared.get(key)
            if nearby and any(abs(index - at) <= DUPLICATE_SPAN for at in nearby):
                continue
        out.append(ev)
    return out


def _subject(ev: Event) -> str:
    """The thing an algorithm event is about, as a comparable string."""
    args = ev.payload.get("args") or {}
    for key in ("node", "value", "target", "v", "index"):
        if key in args:
            value = args[key]
            if isinstance(value, dict):
                value = value.get("v", value.get("r"))
            return f"{key}={value}"
    return ""
