"""Semantic lifting: recovering algorithm-level operations from generic events.

This is mechanism 2 of the two-mechanism design in docs/07 §M.3, and it is the
part that makes the project's central claim testable.  Mechanism 1 (explicit
``algo.*`` calls) works only for code that has been annotated.  Lifting works on
code we do not control -- a student's own bubble sort produces ``SWAP`` events
because the *shape of what the program did* matches the idiom, not because
anyone declared it.

The line we hold:

    matching on the shape of what the program did   -> derivation
    matching on the name of the algorithm           -> hard-coding

No lifter ever sees an algorithm identifier.  ``RelaxLifter`` fires on any
conditional distance improvement -- in Dijkstra, in Bellman-Ford, in a
dynamic-programming relaxation that has nothing to do with graphs.

Every lifted event carries ``meta.origin = "lifted"`` and a confidence, so the
UI can distinguish inferred semantics from recorded ones, and the whole pipeline
can be switched off (which is also the ablation condition for RQ1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core.events import Event, EventType, Loc


@dataclass
class LiftContext:
    """Rolling context shared by the lifters in a pipeline."""

    #: ref -> the most recent heap snapshot seen for it
    heap: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: ref -> friendly name, harvested from event payloads
    names: dict[str, str] = field(default_factory=dict)
    #: recent events, newest last
    window: list[Event] = field(default_factory=list)
    window_size: int = 24

    def observe(self, ev: Event) -> None:
        payload = ev.payload
        ref = payload.get("container_ref") or payload.get("ref")
        name = payload.get("container_name") or payload.get("name")
        if ref and isinstance(name, str) and name:
            self.names.setdefault(ref, name)
        if ev.type == EventType.OBJECT_CREATED and payload.get("snapshot"):
            self.heap[payload["ref"]] = payload["snapshot"]
        elif ev.type == EventType.OBJECT_MUTATED and payload.get("after"):
            self.heap[payload["ref"]] = payload["after"]
        self.window.append(ev)
        if len(self.window) > self.window_size:
            del self.window[0]

    def recent(self, count: int) -> list[Event]:
        return self.window[-count:]


class Lifter(Protocol):
    id: str

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        """Return events to insert immediately after ``ev`` (usually empty)."""

    def reset(self) -> None:
        ...


def algorithm_event(
    name: str,
    args: dict[str, Any],
    source: Event,
    lifter: str,
    confidence: float = 0.9,
    ref: str | None = None,
) -> Event:
    """Build a lifted ``ALGORITHM_EVENT`` in the envelope of the event that triggered it."""
    payload: dict[str, Any] = {"name": name, "args": args}
    if ref:
        payload["ref"] = ref
    return Event(
        id=source.id,
        step=source.step,
        type=EventType.ALGORITHM_EVENT,
        t=source.t,
        frame=source.frame,
        depth=source.depth,
        loc=Loc(source.line) if source.line else None,
        payload=payload,
        meta={"origin": "lifted", "lifter": lifter, "confidence": confidence},
    )
