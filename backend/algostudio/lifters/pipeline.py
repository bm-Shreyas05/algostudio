"""Runs the lifters over a recorded event stream."""

from __future__ import annotations

from typing import Sequence

from ..core.events import Event
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
        return out

    @property
    def ids(self) -> list[str]:
        return [l.id for l in self.lifters]
