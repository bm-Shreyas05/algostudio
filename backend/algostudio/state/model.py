"""The execution state.

Design note that everything else depends on: **the reducer never mutates a
container in place.**  Writes replace the container with a copy
(copy-on-write), so cloning a state for a checkpoint is a set of shallow copies
-- O(number of heap objects), not O(total data size) -- and unchanged objects
are structurally shared between checkpoints.  Without this, checkpointing a
10k-step sort would deep-copy the array 150 times.

Why an explicit heap at all: aliasing is a first-class teaching concept.
``a = [1,2,3]; b = a; b.append(4)`` must render as *one* object with two arrows,
not two independent lists.  Bindings therefore hold refs, and the heap holds
objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import Loc

INFINITE_TTL = 10 ** 9

#: How long an annotation stays visible after the event that created it, by
#: ``ALGORITHM_EVENT`` name.  Transient highlights decay; positional markers
#: persist until superseded.
ANNOTATION_TTL: dict[str, int] = {
    "compare": 3,
    "highlight": 3,
    "swap": 3,
    "relax": 4,
    "discover": 6,
    "note": 8,
    "pointer": INFINITE_TTL,
    "region": INFINITE_TTL,
    "mark": INFINITE_TTL,
    "visit": INFINITE_TTL,
    "pivot": INFINITE_TTL,
    "partition": INFINITE_TTL,
}


@dataclass(slots=True)
class Frame:
    frame_id: int
    func_id: str
    name: str
    depth: int
    call_line: int = 0
    line: int = 0
    args: list[str] = field(default_factory=list)
    locals: dict[str, Any] = field(default_factory=dict)
    return_value: Any = None
    active: bool = True
    parent: int = -1
    exit_reason: str = ""

    def copy(self) -> "Frame":
        # ``locals`` is replaced on write, never mutated, so sharing is safe.
        return Frame(
            self.frame_id, self.func_id, self.name, self.depth, self.call_line,
            self.line, self.args, self.locals, self.return_value, self.active,
            self.parent, self.exit_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "func_id": self.func_id,
            "name": self.name,
            "depth": self.depth,
            "call_line": self.call_line,
            "line": self.line,
            "args": self.args,
            "locals": self.locals,
            "return_value": self.return_value,
            "active": self.active,
            "parent": self.parent,
            "exit_reason": self.exit_reason,
        }


@dataclass(slots=True)
class LoopState:
    loop_id: str
    kind: str
    line: int
    iteration: int = -1
    finished: bool = False
    exit: str = ""

    def copy(self) -> "LoopState":
        return LoopState(self.loop_id, self.kind, self.line, self.iteration,
                         self.finished, self.exit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id, "kind": self.kind, "line": self.line,
            "iteration": self.iteration, "finished": self.finished, "exit": self.exit,
        }


@dataclass(slots=True)
class Annotation:
    """A visual hint produced by an ``ALGORITHM_EVENT``.

    Keyed by the id of the event that created it, so application and inversion
    are exact: an annotation is never *replaced*, only superseded by a later one
    with the same (kind, label, target).  Views resolve the live set.
    """

    event_id: int
    step: int
    kind: str
    target_ref: str | None = None
    label: str = ""
    color: str = ""
    index: int | None = None
    lo: int | None = None
    hi: int | None = None
    value: Any = None
    ttl: int = INFINITE_TTL

    def key(self) -> tuple[str, str, str | None]:
        return (self.kind, self.label, self.target_ref)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "step": self.step, "kind": self.kind,
            "target_ref": self.target_ref, "label": self.label, "color": self.color,
            "index": self.index, "lo": self.lo, "hi": self.hi, "value": self.value,
        }


@dataclass(slots=True)
class ExceptionInfo:
    exc_type: str
    message: str
    line: int = 0
    handled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "exc_type": self.exc_type, "message": self.message,
            "line": self.line, "handled": self.handled,
        }


@dataclass(slots=True)
class CallRecord:
    """One node of the call tree.  Append-only, so checkpoints share the list."""

    frame_id: int
    parent: int
    name: str
    func_id: str
    depth: int
    call_line: int
    enter_step: int
    args: dict[str, Any] = field(default_factory=dict)
    return_value: Any = None
    exit_step: int = -1
    exit_reason: str = ""

    def copy(self) -> "CallRecord":
        return CallRecord(
            self.frame_id, self.parent, self.name, self.func_id, self.depth,
            self.call_line, self.enter_step, self.args, self.return_value,
            self.exit_step, self.exit_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id, "parent": self.parent, "name": self.name,
            "func_id": self.func_id, "depth": self.depth,
            "call_line": self.call_line, "enter_step": self.enter_step,
            "args": self.args, "return_value": self.return_value,
            "exit_step": self.exit_step, "exit_reason": self.exit_reason,
        }


class ExecutionState:
    """Everything the UI, analytics and the AI need at one point in time."""

    __slots__ = (
        "step", "status", "frames", "retired", "heap", "stdout", "stderr",
        "current_loc", "loops", "exception", "annotations", "counters",
        "call_tree", "finished_reason",
    )

    def __init__(self) -> None:
        self.step: int = -1
        self.status: str = "running"
        self.frames: list[Frame] = [Frame(0, "<module>", "<module>", 0)]
        self.retired: dict[int, Frame] = {}
        self.heap: dict[str, dict[str, Any]] = {}
        self.stdout: str = ""
        self.stderr: str = ""
        self.current_loc: Loc | None = None
        self.loops: dict[str, LoopState] = {}
        self.exception: ExceptionInfo | None = None
        self.annotations: dict[int, Annotation] = {}
        self.counters: dict[str, int] = {}
        self.call_tree: list[CallRecord] = []
        self.finished_reason: str = ""

    # -- structure ----------------------------------------------------------
    @property
    def frame(self) -> Frame:
        return self.frames[-1]

    @property
    def globals(self) -> dict[str, Any]:
        return self.frames[0].locals

    @property
    def depth(self) -> int:
        return len(self.frames) - 1

    def clone(self) -> "ExecutionState":
        s = ExecutionState.__new__(ExecutionState)
        s.step = self.step
        s.status = self.status
        s.frames = [f.copy() for f in self.frames]
        s.retired = dict(self.retired)
        s.heap = dict(self.heap)
        s.stdout = self.stdout
        s.stderr = self.stderr
        s.current_loc = self.current_loc
        s.loops = {k: v.copy() for k, v in self.loops.items()}
        s.exception = self.exception
        s.annotations = dict(self.annotations)
        s.counters = dict(self.counters)
        s.call_tree = list(self.call_tree)
        s.finished_reason = self.finished_reason
        return s

    # -- copy-on-write heap helpers ----------------------------------------
    def heap_write(self, ref: str, record: dict[str, Any]) -> None:
        self.heap[ref] = record

    def heap_copy(self, ref: str) -> dict[str, Any] | None:
        """A private copy of a heap record, ready to mutate."""
        rec = self.heap.get(ref)
        if rec is None:
            return None
        new = dict(rec)
        if "items" in new:
            new["items"] = list(new["items"])
        if "entries" in new:
            new["entries"] = [list(e) for e in new["entries"]]
        if "fields" in new:
            new["fields"] = dict(new["fields"])
        return new

    def bind(self, frame: Frame, name: str, value: Any) -> None:
        d = dict(frame.locals)
        d[name] = value
        frame.locals = d

    def unbind(self, frame: Frame, name: str) -> None:
        d = dict(frame.locals)
        d.pop(name, None)
        frame.locals = d

    def frame_for(self, scope: str) -> Frame:
        return self.frames[0] if scope == "global" else self.frames[-1]

    def ref_names(self) -> dict[str, str]:
        """Friendly names for heap objects, derived from live bindings.

        Derived rather than accumulated: a stored name/ref map would need its
        own inverse (which binding first named this object?), and getting that
        wrong is exactly the kind of bug that makes a reconstructed state differ
        from the one that really existed.  Scanning bindings is cheap and always
        correct, so the invariant is free.
        """
        names: dict[str, str] = {}
        # Retired frames first so an active binding wins the name, but an object
        # created inside a function that has already returned still has one --
        # otherwise `dist` inside dijkstra would look unreferenced at the end of
        # the run and lose its place in the view plan.
        for frame in list(self.retired.values()) + self.frames:
            for name, value in frame.locals.items():
                if isinstance(value, dict) and value.get("k") == "ref":
                    names[value["r"]] = name
        return names

    # -- annotations --------------------------------------------------------
    def live_annotations(self) -> list[Annotation]:
        """The visible annotation set: newest per key, expired ones dropped."""
        best: dict[tuple[str, str, str | None], Annotation] = {}
        for ann in self.annotations.values():
            if self.step - ann.step > ann.ttl:
                continue
            key = ann.key()
            current = best.get(key)
            if current is None or ann.step > current.step:
                best[key] = ann
        return sorted(best.values(), key=lambda a: a.step)

    # -- serialization ------------------------------------------------------
    def to_dict(self, include_heap: bool = True) -> dict[str, Any]:
        d: dict[str, Any] = {
            "step": self.step,
            "status": self.status,
            "current_loc": self.current_loc.to_dict() if self.current_loc else None,
            "frames": [f.to_dict() for f in self.frames],
            "globals": self.globals,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "loops": {k: v.to_dict() for k, v in self.loops.items()},
            "exception": self.exception.to_dict() if self.exception else None,
            "annotations": [a.to_dict() for a in self.live_annotations()],
            "counters": self.counters,
            "call_tree": [c.to_dict() for c in self.call_tree],
            "names": self.ref_names(),
            "depth": self.depth,
        }
        if include_heap:
            d["heap"] = self.heap
        return d
