"""The event vocabulary.

This module is the contract between every other part of the system: the sandbox
child that produces events, the reducer that consumes them, the lifters that
synthesize them, and the frontend that renders them.

Rules (see docs/02-event-model.md):
  * stdlib only -- this module is imported inside the sandbox.
  * every mutating event carries enough information to be inverted.
  * unknown event types must never be an error for a reader.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1


class EventType(str, Enum):
    # ---- Tier 0: lifecycle -------------------------------------------------
    PROGRAM_STARTED = "PROGRAM_STARTED"
    PROGRAM_FINISHED = "PROGRAM_FINISHED"
    STDOUT_WRITE = "STDOUT_WRITE"
    STDERR_WRITE = "STDERR_WRITE"
    STDIN_READ = "STDIN_READ"

    # ---- Tier 1: control flow ---------------------------------------------
    LINE_EXECUTED = "LINE_EXECUTED"
    CONDITION_EVALUATED = "CONDITION_EVALUATED"
    BRANCH_TAKEN = "BRANCH_TAKEN"
    LOOP_STARTED = "LOOP_STARTED"
    LOOP_ITERATION = "LOOP_ITERATION"
    LOOP_FINISHED = "LOOP_FINISHED"
    FUNCTION_ENTERED = "FUNCTION_ENTERED"
    FUNCTION_RETURNED = "FUNCTION_RETURNED"
    FUNCTION_EXITED = "FUNCTION_EXITED"
    EXCEPTION_RAISED = "EXCEPTION_RAISED"
    EXCEPTION_HANDLED = "EXCEPTION_HANDLED"

    # ---- Tier 2: data (invertible core) -----------------------------------
    VARIABLE_CREATED = "VARIABLE_CREATED"
    VARIABLE_WRITTEN = "VARIABLE_WRITTEN"
    VARIABLE_READ = "VARIABLE_READ"
    VARIABLE_DELETED = "VARIABLE_DELETED"
    SUBSCRIPT_READ = "SUBSCRIPT_READ"
    SUBSCRIPT_WRITTEN = "SUBSCRIPT_WRITTEN"
    SUBSCRIPT_DELETED = "SUBSCRIPT_DELETED"
    ATTRIBUTE_READ = "ATTRIBUTE_READ"
    ATTRIBUTE_WRITTEN = "ATTRIBUTE_WRITTEN"
    OBJECT_CREATED = "OBJECT_CREATED"
    OBJECT_MUTATED = "OBJECT_MUTATED"
    OBJECT_FREED = "OBJECT_FREED"
    EXPRESSION_EVALUATED = "EXPRESSION_EVALUATED"

    # ---- Tier 3: structural collections (projections) ----------------------
    COLLECTION_CREATED = "COLLECTION_CREATED"
    COLLECTION_RESIZED = "COLLECTION_RESIZED"
    STACK_PUSH = "STACK_PUSH"
    STACK_POP = "STACK_POP"
    QUEUE_ENQUEUE = "QUEUE_ENQUEUE"
    QUEUE_DEQUEUE = "QUEUE_DEQUEUE"

    # ---- Tier 4: algorithm level (open set via payload["name"]) ------------
    ALGORITHM_EVENT = "ALGORITHM_EVENT"

    # ---- Tier 5: harness ---------------------------------------------------
    BUDGET_WARNING = "BUDGET_WARNING"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    INSTRUMENTATION_SKIPPED = "INSTRUMENTATION_SKIPPED"
    SNAPSHOT = "SNAPSHOT"


#: Events whose application changes ``ExecutionState`` in a way that must be
#: undoable.  Every member here needs both an ``apply`` and an ``unapply``
#: handler; ``tests/unit/test_reducer_coverage.py`` enforces that.
MUTATING: frozenset[EventType] = frozenset(
    {
        EventType.VARIABLE_CREATED,
        EventType.VARIABLE_WRITTEN,
        EventType.VARIABLE_DELETED,
        EventType.SUBSCRIPT_WRITTEN,
        EventType.SUBSCRIPT_DELETED,
        EventType.ATTRIBUTE_WRITTEN,
        EventType.OBJECT_CREATED,
        EventType.OBJECT_MUTATED,
        EventType.OBJECT_FREED,
        EventType.FUNCTION_ENTERED,
        EventType.FUNCTION_RETURNED,
        EventType.FUNCTION_EXITED,
        EventType.LOOP_STARTED,
        EventType.LOOP_ITERATION,
        EventType.LOOP_FINISHED,
        EventType.STDOUT_WRITE,
        EventType.STDERR_WRITE,
        EventType.EXCEPTION_RAISED,
        EventType.EXCEPTION_HANDLED,
        EventType.COLLECTION_CREATED,
        EventType.ALGORITHM_EVENT,
        EventType.PROGRAM_STARTED,
        EventType.PROGRAM_FINISHED,
        EventType.BUDGET_EXCEEDED,
    }
)

#: Categories drive timeline filter chips in the UI.
CATEGORY: dict[EventType, str] = {
    EventType.PROGRAM_STARTED: "lifecycle",
    EventType.PROGRAM_FINISHED: "lifecycle",
    EventType.BUDGET_WARNING: "lifecycle",
    EventType.BUDGET_EXCEEDED: "lifecycle",
    EventType.INSTRUMENTATION_SKIPPED: "lifecycle",
    EventType.SNAPSHOT: "lifecycle",
    EventType.STDOUT_WRITE: "io",
    EventType.STDERR_WRITE: "io",
    EventType.STDIN_READ: "io",
    EventType.LINE_EXECUTED: "flow",
    EventType.CONDITION_EVALUATED: "flow",
    EventType.BRANCH_TAKEN: "flow",
    EventType.LOOP_STARTED: "loop",
    EventType.LOOP_ITERATION: "loop",
    EventType.LOOP_FINISHED: "loop",
    EventType.FUNCTION_ENTERED: "call",
    EventType.FUNCTION_RETURNED: "call",
    EventType.FUNCTION_EXITED: "call",
    EventType.EXCEPTION_RAISED: "error",
    EventType.EXCEPTION_HANDLED: "error",
    EventType.VARIABLE_CREATED: "data",
    EventType.VARIABLE_WRITTEN: "data",
    EventType.VARIABLE_READ: "read",
    EventType.VARIABLE_DELETED: "data",
    EventType.SUBSCRIPT_READ: "read",
    EventType.SUBSCRIPT_WRITTEN: "data",
    EventType.SUBSCRIPT_DELETED: "data",
    EventType.ATTRIBUTE_READ: "read",
    EventType.ATTRIBUTE_WRITTEN: "data",
    EventType.OBJECT_CREATED: "heap",
    EventType.OBJECT_MUTATED: "heap",
    EventType.OBJECT_FREED: "heap",
    EventType.EXPRESSION_EVALUATED: "expr",
    EventType.COLLECTION_CREATED: "heap",
    EventType.COLLECTION_RESIZED: "heap",
    EventType.STACK_PUSH: "structure",
    EventType.STACK_POP: "structure",
    EventType.QUEUE_ENQUEUE: "structure",
    EventType.QUEUE_DEQUEUE: "structure",
    EventType.ALGORITHM_EVENT: "algorithm",
}

#: ``ALGORITHM_EVENT`` names with defined meaning for the built-in views.  An
#: unrecognised name is carried through and rendered generically -- never an
#: error (schema rule C5).
KNOWN_ALGORITHM_EVENTS = frozenset(
    {
        "compare", "swap", "visit", "discover", "relax", "enqueue", "dequeue",
        "push", "pop", "partition", "merge", "pivot", "mark", "unmark",
        "highlight", "annotate", "region", "pointer", "metric", "note",
    }
)


@dataclass(frozen=True, slots=True)
class Loc:
    """A span in the *original* source, never in instrumented source."""

    line: int
    col: int = 0
    end_line: int = 0
    end_col: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "line": self.line,
            "col": self.col,
            "end_line": self.end_line or self.line,
            "end_col": self.end_col,
        }

    @staticmethod
    def from_dict(d: dict[str, Any] | None) -> "Loc | None":
        if not d:
            return None
        return Loc(
            int(d.get("line", 0)),
            int(d.get("col", 0)),
            int(d.get("end_line", 0)),
            int(d.get("end_col", 0)),
        )


@dataclass(slots=True)
class Event:
    """One observation of the running program.

    ``id`` is the dense index within the execution; ``step`` is the logical
    clock.  They coincide for recorded events but diverge for lifted events,
    which are inserted with the step of the raw event that produced them.
    """

    id: int
    step: int
    type: EventType
    t: float = 0.0
    frame: int = 0
    depth: int = 0
    loc: Loc | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    # -- serialization ------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "step": self.step,
            "type": self.type.value if isinstance(self.type, EventType) else self.type,
            "t": round(self.t, 6),
            "frame": self.frame,
            "depth": self.depth,
            "payload": self.payload,
        }
        if self.loc is not None:
            d["loc"] = self.loc.to_dict()
        if self.meta:
            d["meta"] = self.meta
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), default=str)

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Event":
        raw_type = d["type"]
        try:
            etype = EventType(raw_type)
        except ValueError:
            # Forward compatibility: unknown types survive as opaque records.
            etype = raw_type  # type: ignore[assignment]
        return Event(
            id=int(d.get("id", 0)),
            step=int(d.get("step", d.get("id", 0))),
            type=etype,
            t=float(d.get("t", 0.0)),
            frame=int(d.get("frame", 0)),
            depth=int(d.get("depth", 0)),
            loc=Loc.from_dict(d.get("loc")),
            payload=d.get("payload") or {},
            meta=d.get("meta") or {},
        )

    @staticmethod
    def from_json(s: str) -> "Event":
        return Event.from_dict(json.loads(s))

    # -- convenience --------------------------------------------------------
    @property
    def category(self) -> str:
        return CATEGORY.get(self.type, "other")  # type: ignore[arg-type]

    @property
    def line(self) -> int:
        return self.loc.line if self.loc else 0

    @property
    def origin(self) -> str:
        return self.meta.get("origin", "runtime")

    @property
    def algorithm_name(self) -> str | None:
        if self.type == EventType.ALGORITHM_EVENT:
            return self.payload.get("name")
        return None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        tname = self.type.value if isinstance(self.type, EventType) else self.type
        extra = ""
        if self.type == EventType.ALGORITHM_EVENT:
            extra = f":{self.payload.get('name')}"
        return f"<Event #{self.id}@{self.step} {tname}{extra} line={self.line}>"


def summarize(ev: Event) -> str:
    """A one-line human description, used by the timeline and the AI context.

    Kept here (rather than in the UI) so the server, the template explainer and
    the frontend all describe an event the same way.
    """
    p = ev.payload
    t = ev.type

    def v(x: Any) -> str:
        return preview(x)

    if t == EventType.LINE_EXECUTED:
        return f"line {ev.line}"
    if t == EventType.VARIABLE_CREATED:
        return f"{p.get('name')} = {v(p.get('value'))}"
    if t == EventType.VARIABLE_WRITTEN:
        return f"{p.get('name')}: {v(p.get('old'))} -> {v(p.get('new'))}"
    if t == EventType.VARIABLE_READ:
        return f"read {p.get('name')} = {v(p.get('value'))}"
    if t == EventType.VARIABLE_DELETED:
        return f"del {p.get('name')}"
    if t == EventType.SUBSCRIPT_READ:
        return f"{p.get('container_name') or p.get('container_ref')}[{p.get('index')}] -> {v(p.get('value'))}"
    if t == EventType.SUBSCRIPT_WRITTEN:
        name = p.get("container_name") or p.get("container_ref")
        return f"{name}[{p.get('index')}]: {v(p.get('old'))} -> {v(p.get('new'))}"
    if t == EventType.SUBSCRIPT_DELETED:
        return f"del {p.get('container_name') or p.get('container_ref')}[{p.get('index')}]"
    if t == EventType.ATTRIBUTE_WRITTEN:
        return f".{p.get('name')}: {v(p.get('old'))} -> {v(p.get('new'))}"
    if t == EventType.CONDITION_EVALUATED:
        return f"{p.get('expr')} -> {p.get('result')}"
    if t == EventType.BRANCH_TAKEN:
        return f"branch: {p.get('branch')}"
    if t == EventType.LOOP_STARTED:
        return f"{p.get('kind')} loop starts"
    if t == EventType.LOOP_ITERATION:
        var = p.get("var")
        if var:
            return f"iteration {p.get('iteration')} ({var} = {v(p.get('value'))})"
        return f"iteration {p.get('iteration')}"
    if t == EventType.LOOP_FINISHED:
        return f"loop ends after {p.get('iterations')} ({p.get('exit')})"
    if t == EventType.FUNCTION_ENTERED:
        args = p.get("args") or {}
        rendered = ", ".join(f"{k}={v(val)}" for k, val in args.items())
        return f"call {p.get('name')}({rendered})"
    if t == EventType.FUNCTION_RETURNED:
        return f"return {v(p.get('value'))}"
    if t == EventType.FUNCTION_EXITED:
        return f"exit {p.get('name', '')} ({p.get('reason')})"
    if t == EventType.EXPRESSION_EVALUATED:
        ops = p.get("operands") or []
        if p.get("op") and len(ops) == 2:
            return f"{v(ops[0])} {p['op']} {v(ops[1])} = {v(p.get('value'))}"
        return f"{p.get('expr', 'expr')} = {v(p.get('value'))}"
    if t == EventType.OBJECT_MUTATED:
        return f"{p.get('name') or p.get('ref')}.{p.get('op')}(...)"
    if t == EventType.OBJECT_CREATED:
        return f"new {p.get('kind')} {p.get('ref')}"
    if t == EventType.STDOUT_WRITE:
        return "print " + (p.get("text") or "").rstrip("\n")[:60]
    if t == EventType.EXCEPTION_RAISED:
        return f"{p.get('exc_type')}: {p.get('message')}"
    if t == EventType.ALGORITHM_EVENT:
        return _summarize_algorithm(p)
    if t == EventType.PROGRAM_STARTED:
        return "program started"
    if t == EventType.PROGRAM_FINISHED:
        return f"program finished ({p.get('status')})"
    if t == EventType.BUDGET_EXCEEDED:
        return f"budget exceeded: {p.get('reason')}"
    if t == EventType.INSTRUMENTATION_SKIPPED:
        return f"reduced detail: {p.get('reason')}"
    if t in (EventType.STACK_PUSH, EventType.QUEUE_ENQUEUE):
        return f"push {v(p.get('value'))}"
    if t in (EventType.STACK_POP, EventType.QUEUE_DEQUEUE):
        return f"pop {v(p.get('value'))}"
    tname = t.value if isinstance(t, EventType) else str(t)
    return tname.lower().replace("_", " ")


def _summarize_algorithm(p: dict[str, Any]) -> str:
    name = p.get("name", "?")
    a = p.get("args") or {}
    if name == "swap":
        return f"swap [{a.get('i')}] <-> [{a.get('j')}]"
    if name == "compare":
        where = ""
        if a.get("i") is not None and a.get("j") is not None:
            where = f" [{a['i']}] vs [{a['j']}]"
        elif a.get("i") is not None:
            where = f" [{a['i']}]"
        return (f"compare{where} {preview(a.get('a'))} {a.get('op', 'vs')} "
                f"{preview(a.get('b'))} -> {a.get('result')}")
    if name == "visit":
        return f"visit {preview(a.get('node'))}"
    if name == "relax":
        improved = " (improved)" if a.get("improved") else ""
        return f"relax {a.get('u')} -> {a.get('v')} w={a.get('weight')}{improved}"
    if name == "pointer":
        return f"pointer {a.get('label')} -> [{a.get('index')}]"
    if name == "region":
        return f"region {a.get('label')} [{a.get('lo')}..{a.get('hi')}]"
    if name in ("enqueue", "push"):
        return f"{name} {preview(a.get('value'))}"
    if name in ("dequeue", "pop"):
        return f"{name} -> {preview(a.get('value'))}"
    if name == "note":
        return str(a.get("text", ""))
    if name == "metric":
        return f"metric {a.get('name')} +{a.get('delta', 1)}"
    return f"{name}({', '.join(f'{k}={preview(x)}' for k, x in a.items())})"


def preview(encoded: Any, maxlen: int = 40) -> str:
    """Render an EncodedValue (or a plain value) compactly for text output."""
    if encoded is None:
        return "?"
    if not isinstance(encoded, dict):
        s = repr(encoded)
        return s if len(s) <= maxlen else s[: maxlen - 1] + "…"
    k = encoded.get("k")
    if k == "none":
        return "None"
    if k in ("int", "float", "bool"):
        # inf/nan are not valid JSON, so the encoder parks them in "special".
        if encoded.get("v") is None and encoded.get("special"):
            return str(encoded["special"])
        return repr(encoded.get("v"))
    if k == "str":
        s = encoded.get("v", "")
        body = s if len(s) <= maxlen else s[: maxlen - 1] + "…"
        return repr(body)
    if k == "ref":
        return f"<{encoded.get('t')} #{encoded.get('r')} len={encoded.get('n')}>"
    if k == "cycle":
        return f"<cycle -> {encoded.get('r')}>"
    if k == "opaque":
        return str(encoded.get("repr", f"<{encoded.get('t')}>"))[:maxlen]
    return str(encoded)[:maxlen]
