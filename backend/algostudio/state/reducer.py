"""R and R': the forward and inverse reducers.

Two dispatch tables keyed on ``EventType``.  Adding an event type adds a table
entry and changes nothing else -- this is what keeps the reducer total and what
makes an unknown event type a no-op rather than a crash (schema rule C5).

The inverse reducer is the reason ``VARIABLE_WRITTEN`` carries both ``old`` and
``new``, and the reason ``OBJECT_MUTATED`` carries ``before`` and ``after``:
with those, stepping backwards is O(1) rather than a replay from a checkpoint.
``tests/property/test_reducer_inverse.py`` asserts ``unapply(apply(s,e),e) == s``
over generated event sequences.
"""

from __future__ import annotations

from typing import Any, Callable

from ..core.events import Event, EventType, Loc
from .model import (
    ANNOTATION_TTL, INFINITE_TTL, Annotation, CallRecord, ExceptionInfo,
    ExecutionState, Frame, LoopState, annotation_subject,
)

Handler = Callable[[ExecutionState, Event], None]

#: Counter bumped by each event type, for the live analytics readout.
_COUNTER_FOR: dict[EventType, str] = {
    EventType.LINE_EXECUTED: "statements",
    EventType.VARIABLE_WRITTEN: "variable_writes",
    EventType.VARIABLE_CREATED: "variable_writes",
    EventType.VARIABLE_READ: "variable_reads",
    EventType.SUBSCRIPT_READ: "array_reads",
    EventType.SUBSCRIPT_WRITTEN: "array_writes",
    EventType.FUNCTION_ENTERED: "function_calls",
    EventType.LOOP_ITERATION: "loop_iterations",
    EventType.CONDITION_EVALUATED: "conditions",
    EventType.OBJECT_MUTATED: "mutations",
}


# ======================================================================
# forward
# ======================================================================
def apply(state: ExecutionState, ev: Event) -> ExecutionState:
    handler = _FORWARD.get(ev.type)  # type: ignore[arg-type]
    if handler is not None:
        handler(state, ev)
    if ev.loc is not None:
        state.current_loc = ev.loc
        _set_frame_line(state, ev.frame, ev.loc.line)
    counter = _COUNTER_FOR.get(ev.type)  # type: ignore[arg-type]
    if counter:
        state.counters[counter] = state.counters.get(counter, 0) + 1
    state.step = ev.id
    return state


def unapply(state: ExecutionState, ev: Event, prev: Event | None = None) -> ExecutionState:
    handler = _INVERSE.get(ev.type)  # type: ignore[arg-type]
    if handler is not None:
        handler(state, ev)
    counter = _COUNTER_FOR.get(ev.type)  # type: ignore[arg-type]
    if counter:
        state.counters[counter] = state.counters.get(counter, 0) - 1
        if state.counters[counter] <= 0:
            del state.counters[counter]
    # Location is sticky, so restore it from what this event displaced rather
    # than from the previous event (which may carry no location at all).
    if ev.loc is not None:
        prev_line = ev.meta.get("pl", 0)
        state.current_loc = Loc(prev_line) if prev_line else None
        _set_frame_line(state, ev.frame, ev.meta.get("pfl", 0))
    state.step = prev.id if prev is not None else -1
    return state


def _set_frame_line(state: ExecutionState, frame_id: int, line: int) -> None:
    """Attribute a line to the frame the event belongs to.

    Looked up by id rather than taking the top of stack: a FUNCTION_EXITED
    event belongs to the frame the handler has just popped, and assigning its
    line to the caller would overwrite the call site.
    """
    top = state.frames[-1]
    if top.frame_id == frame_id:
        top.line = line
        return
    for frame in reversed(state.frames):
        if frame.frame_id == frame_id:
            frame.line = line
            return


# ======================================================================
# variables
# ======================================================================
def _target_frame(state: ExecutionState, ev: Event):
    """The frame a binding event belongs to.

    Routed by ``ev.frame`` rather than by the top of stack: the two can differ
    while unwinding, and binding to the wrong frame is invisible going forward
    but corrupts the state on the way back.
    """
    if ev.payload.get("scope") == "global":
        return state.frames[0]
    for frame in reversed(state.frames):
        if frame.frame_id == ev.frame:
            return frame
    return state.frames[-1]


def _f_var_created(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    s.bind(_target_frame(s, ev), p["name"], p.get("value"))


def _i_var_created(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    s.unbind(_target_frame(s, ev), p["name"])


def _f_var_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    frame = _target_frame(s, ev)
    # A closure variable is live in the interpreter's frame from the start, so
    # the probe reports a write ("13 -> 16", which is the useful thing to show)
    # even though the name is appearing in *our* frame model for the first time.
    # Record that, so undoing removes the binding instead of leaving a stale one.
    if p["name"] not in frame.locals:
        ev.meta["_undo_unbind"] = True
    s.bind(frame, p["name"], p.get("new"))


def _i_var_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    frame = _target_frame(s, ev)
    if ev.meta.get("_undo_unbind"):
        s.unbind(frame, p["name"])
    else:
        s.bind(frame, p["name"], p.get("old"))


def _f_var_deleted(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    frame = _target_frame(s, ev)
    if p["name"] not in frame.locals:
        ev.meta["_undo_absent"] = True
    s.unbind(frame, p["name"])


def _i_var_deleted(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    if ev.meta.get("_undo_absent"):
        return
    s.bind(_target_frame(s, ev), p["name"], p.get("old"))


# ======================================================================
# heap
# ======================================================================
def _f_object_created(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    s.heap_write(p["ref"], p.get("snapshot") or {"ref": p["ref"], "t": p.get("kind")})


def _i_object_created(s: ExecutionState, ev: Event) -> None:
    s.heap.pop(ev.payload["ref"], None)


def _f_object_mutated(s: ExecutionState, ev: Event) -> None:
    after = ev.payload.get("after")
    if after:
        s.heap_write(ev.payload["ref"], after)


def _i_object_mutated(s: ExecutionState, ev: Event) -> None:
    before = ev.payload.get("before")
    if before is not None:
        s.heap_write(ev.payload["ref"], before)


def _f_object_freed(s: ExecutionState, ev: Event) -> None:
    s.heap.pop(ev.payload["ref"], None)


def _i_object_freed(s: ExecutionState, ev: Event) -> None:
    snap = ev.payload.get("snapshot")
    if snap:
        s.heap_write(ev.payload["ref"], snap)


def _f_subscript_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    _set_index(s, p.get("container_ref"), p.get("index"), p.get("new"), insert=not p.get("existed", True))


def _i_subscript_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    if p.get("existed", True):
        _set_index(s, p.get("container_ref"), p.get("index"), p.get("old"))
    else:
        _del_index(s, p.get("container_ref"), p.get("index"))


def _f_subscript_deleted(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    _del_index(s, p.get("container_ref"), p.get("index"))


def _i_subscript_deleted(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    _set_index(s, p.get("container_ref"), p.get("index"), p.get("old"),
               insert=True, position=p.get("position"))


def _f_attribute_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    rec = s.heap_copy(p.get("object_ref", ""))
    if rec is None:
        return
    fields = rec.setdefault("fields", {})
    fields[p["name"]] = p.get("new")
    rec["n"] = len(fields)
    s.heap_write(p["object_ref"], rec)


def _i_attribute_written(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    rec = s.heap_copy(p.get("object_ref", ""))
    if rec is None:
        return
    fields = rec.setdefault("fields", {})
    if p.get("existed", True):
        fields[p["name"]] = p.get("old")
    else:
        fields.pop(p["name"], None)
    rec["n"] = len(fields)
    s.heap_write(p["object_ref"], rec)


def _set_index(s: ExecutionState, ref: str | None, index: Any, value: Any,
               insert: bool = False, position: int | None = None) -> None:
    if not ref:
        return
    rec = s.heap_copy(ref)
    if rec is None:
        return
    tag = rec.get("t")
    if "items" in rec or tag in ("list", "tuple", "deque", "array"):
        items = rec.setdefault("items", [])
        if isinstance(index, int):
            pos = index if index >= 0 else len(index_base(rec, items)) + index
            if pos >= len(items) and rec.get("trunc"):
                # The write lands beyond the encoder's stored window.  The
                # record already advertises truncation, so growing it here would
                # invent elements that the view would render as real.
                return
            if insert or pos >= len(items):
                at = position if position is not None else pos
                at = max(0, min(at, len(items)))
                items.insert(at, value)
                rec["n"] = rec.get("n", len(items) - 1) + 1
            else:
                items[pos] = value
                rec["n"] = max(rec.get("n", 0), len(items))
    else:
        entries = rec.setdefault("entries", [])
        key = _encode_key(index)
        for pair in entries:
            if _key_equal(pair[0], index):
                pair[1] = value
                break
        else:
            at = position if position is not None else len(entries)
            entries.insert(max(0, min(at, len(entries))), [key, value])
        rec["n"] = len(entries)
    s.heap_write(ref, rec)


def _del_index(s: ExecutionState, ref: str | None, index: Any) -> None:
    if not ref:
        return
    rec = s.heap_copy(ref)
    if rec is None:
        return
    if "items" in rec:
        items = rec["items"]
        if isinstance(index, int):
            pos = index if index >= 0 else len(items) + index
            if 0 <= pos < len(items):
                del items[pos]
        rec["n"] = len(items)
    elif "entries" in rec:
        rec["entries"] = [p for p in rec["entries"] if not _key_equal(p[0], index)]
        rec["n"] = len(rec["entries"])
    s.heap_write(ref, rec)


def index_base(rec: dict[str, Any], items: list[Any]) -> list[Any]:
    """Length basis for negative indices: the true length, not the stored window."""
    n = rec.get("n")
    return items if not isinstance(n, int) or n <= len(items) else [None] * n


def _encode_key(index: Any) -> dict[str, Any]:
    if isinstance(index, bool):
        return {"k": "bool", "v": index}
    if isinstance(index, int):
        return {"k": "int", "v": index}
    if isinstance(index, float):
        return {"k": "float", "v": index}
    return {"k": "str", "v": str(index), "len": len(str(index))}


def _key_equal(encoded: Any, index: Any) -> bool:
    if not isinstance(encoded, dict):
        return encoded == index
    return encoded.get("v") == index or str(encoded.get("v")) == str(index)


# ======================================================================
# control flow
# ======================================================================
def _f_function_entered(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    args = p.get("args") or {}
    frame = Frame(
        frame_id=ev.frame,
        func_id=p.get("func_id", ""),
        name=p.get("name", "?"),
        depth=ev.depth,
        call_line=p.get("call_line", 0),
        line=ev.line,
        args=list(args),
        locals=dict(args),
        parent=p.get("caller_frame", -1),
    )
    s.frames.append(frame)
    s.call_tree.append(
        CallRecord(
            frame_id=frame.frame_id, parent=frame.parent, name=frame.name,
            func_id=frame.func_id, depth=frame.depth,
            call_line=frame.call_line, enter_step=ev.id, args=dict(args),
        )
    )


def _i_function_entered(s: ExecutionState, ev: Event) -> None:
    if len(s.frames) > 1:
        s.frames.pop()
    if s.call_tree and s.call_tree[-1].enter_step == ev.id:
        s.call_tree.pop()


def _update_call(s: ExecutionState, frame_id: int, **changes: Any) -> None:
    """Replace a call-tree record rather than mutating it.

    ``clone()`` shallow-copies the call-tree *list*, so the records themselves
    are shared between checkpoints.  Mutating one in place would retroactively
    change every checkpoint that shares it -- a subtle way to make time travel
    show a state that never existed.
    """
    for i in range(len(s.call_tree) - 1, -1, -1):
        if s.call_tree[i].frame_id == frame_id:
            rec = s.call_tree[i].copy()
            for key, value in changes.items():
                setattr(rec, key, value)
            s.call_tree[i] = rec
            return


def _f_function_returned(s: ExecutionState, ev: Event) -> None:
    s.frame.return_value = ev.payload.get("value")
    _update_call(s, s.frame.frame_id, return_value=ev.payload.get("value"))


def _i_function_returned(s: ExecutionState, ev: Event) -> None:
    s.frame.return_value = None
    _update_call(s, s.frame.frame_id, return_value=None)


def _f_function_exited(s: ExecutionState, ev: Event) -> None:
    if len(s.frames) <= 1:
        return
    frame = s.frames.pop()
    frame.active = False
    frame.exit_reason = ev.payload.get("reason", "return")
    # Retired frames are never mutated again, so checkpoints share them and
    # inversion can restore the exact frame including its locals.
    s.retired[frame.frame_id] = frame
    _update_call(s, frame.frame_id, exit_step=ev.id, exit_reason=frame.exit_reason)


def _i_function_exited(s: ExecutionState, ev: Event) -> None:
    frame_id = ev.frame
    frame = s.retired.pop(frame_id, None)
    if frame is None:
        return
    restored = frame.copy()
    restored.active = True
    restored.exit_reason = ""
    s.frames.append(restored)
    _update_call(s, frame_id, exit_step=-1, exit_reason="")


def _f_loop_started(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    lid = p["loop_id"]
    # A loop can start more than once -- a nested loop, or a loop inside a
    # function called twice.  The displaced LoopState is stashed on the event so
    # the inverse can restore it rather than deleting the entry outright.
    # Safe because the displaced value is deterministic for a given event, and
    # Timeline._build applies every event once before any backward step.
    if lid in s.loops:
        ev.meta["_undo_loop"] = s.loops[lid].to_dict()
    s.loops[lid] = LoopState(lid, p.get("kind", "for"), ev.line)


def _i_loop_started(s: ExecutionState, ev: Event) -> None:
    lid = ev.payload["loop_id"]
    previous = ev.meta.get("_undo_loop")
    if previous:
        s.loops[lid] = LoopState(
            previous["loop_id"], previous["kind"], previous["line"],
            previous["iteration"], previous["finished"], previous["exit"],
        )
    else:
        s.loops.pop(lid, None)


def _f_loop_iteration(s: ExecutionState, ev: Event) -> None:
    loop = s.loops.get(ev.payload["loop_id"])
    if loop is not None:
        loop.iteration = ev.payload.get("iteration", loop.iteration + 1)


def _i_loop_iteration(s: ExecutionState, ev: Event) -> None:
    loop = s.loops.get(ev.payload["loop_id"])
    if loop is not None:
        loop.iteration = ev.payload.get("iteration", 0) - 1


def _f_loop_finished(s: ExecutionState, ev: Event) -> None:
    loop = s.loops.get(ev.payload["loop_id"])
    if loop is not None:
        loop.finished = True
        loop.exit = ev.payload.get("exit", "normal")


def _i_loop_finished(s: ExecutionState, ev: Event) -> None:
    loop = s.loops.get(ev.payload["loop_id"])
    if loop is not None:
        loop.finished = False
        loop.exit = ""


# ======================================================================
# io, lifecycle, exceptions
# ======================================================================
def _f_stdout(s: ExecutionState, ev: Event) -> None:
    s.stdout += ev.payload.get("text", "")


def _i_stdout(s: ExecutionState, ev: Event) -> None:
    text = ev.payload.get("text", "")
    if text and s.stdout.endswith(text):
        s.stdout = s.stdout[: -len(text)]


def _f_stderr(s: ExecutionState, ev: Event) -> None:
    s.stderr += ev.payload.get("text", "")


def _i_stderr(s: ExecutionState, ev: Event) -> None:
    text = ev.payload.get("text", "")
    if text and s.stderr.endswith(text):
        s.stderr = s.stderr[: -len(text)]


def _f_exception_raised(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    s.exception = ExceptionInfo(
        p.get("exc_type", "Exception"), p.get("message", ""), ev.line
    )


def _i_exception_raised(s: ExecutionState, ev: Event) -> None:
    s.exception = None


def _f_exception_handled(s: ExecutionState, ev: Event) -> None:
    if s.exception is not None:
        s.exception = ExceptionInfo(
            s.exception.exc_type, s.exception.message, s.exception.line, handled=True
        )


def _i_exception_handled(s: ExecutionState, ev: Event) -> None:
    if s.exception is not None:
        s.exception = ExceptionInfo(
            s.exception.exc_type, s.exception.message, s.exception.line, handled=False
        )


def _f_program_started(s: ExecutionState, ev: Event) -> None:
    s.status = "running"


def _i_program_started(s: ExecutionState, ev: Event) -> None:
    s.status = "running"


def _f_program_finished(s: ExecutionState, ev: Event) -> None:
    s.status = ev.payload.get("status", "ok")
    s.finished_reason = ev.payload.get("status", "")


def _i_program_finished(s: ExecutionState, ev: Event) -> None:
    s.status = "running"
    s.finished_reason = ""


def _f_budget_exceeded(s: ExecutionState, ev: Event) -> None:
    s.status = "budget_exceeded"


def _i_budget_exceeded(s: ExecutionState, ev: Event) -> None:
    s.status = "running"


# ======================================================================
# algorithm events -> annotations
# ======================================================================
_ANNOTATION_KINDS = {
    "pointer", "region", "mark", "unmark", "highlight", "visit", "discover",
    "compare", "swap", "relax", "pivot", "partition", "note",
}


def _f_algorithm(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    name = p.get("name", "")
    s.counters[f"algo.{name}"] = s.counters.get(f"algo.{name}", 0) + 1
    if name == "metric":
        args = p.get("args") or {}
        key = str(args.get("name", "metric"))
        s.counters[key] = s.counters.get(key, 0) + int(args.get("delta", 1))
        return
    if name not in _ANNOTATION_KINDS:
        return
    args = p.get("args") or {}
    ann = Annotation(
        event_id=ev.id,
        step=ev.id,
        kind=name,
        target_ref=p.get("ref"),
        label=str(args.get("label") or args.get("text") or name),
        color=str(args.get("color") or ""),
        index=_int_or_none(args.get("index") if "index" in args else args.get("i")),
        lo=_int_or_none(args.get("lo")),
        hi=_int_or_none(args.get("hi")),
        value=args,
        ttl=ANNOTATION_TTL.get(name, INFINITE_TTL),
        subject=annotation_subject(name, args),
    )
    s.annotations[ev.id] = ann


def _i_algorithm(s: ExecutionState, ev: Event) -> None:
    p = ev.payload
    name = p.get("name", "")
    key = f"algo.{name}"
    if key in s.counters:
        s.counters[key] -= 1
        if s.counters[key] <= 0:
            del s.counters[key]
    if name == "metric":
        args = p.get("args") or {}
        mkey = str(args.get("name", "metric"))
        if mkey in s.counters:
            s.counters[mkey] -= int(args.get("delta", 1))
            if s.counters[mkey] <= 0:
                del s.counters[mkey]
        return
    s.annotations.pop(ev.id, None)


def _int_or_none(v: Any) -> int | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, dict) and v.get("k") == "int":
        return v.get("v")
    return None


# ======================================================================
# structural projections (advisory; the authoritative mutation is elsewhere)
# ======================================================================
def _noop(s: ExecutionState, ev: Event) -> None:
    return None


_FORWARD: dict[EventType, Handler] = {
    EventType.PROGRAM_STARTED: _f_program_started,
    EventType.PROGRAM_FINISHED: _f_program_finished,
    EventType.BUDGET_EXCEEDED: _f_budget_exceeded,
    EventType.STDOUT_WRITE: _f_stdout,
    EventType.STDERR_WRITE: _f_stderr,
    EventType.VARIABLE_CREATED: _f_var_created,
    EventType.VARIABLE_WRITTEN: _f_var_written,
    EventType.VARIABLE_DELETED: _f_var_deleted,
    EventType.SUBSCRIPT_WRITTEN: _f_subscript_written,
    EventType.SUBSCRIPT_DELETED: _f_subscript_deleted,
    EventType.ATTRIBUTE_WRITTEN: _f_attribute_written,
    EventType.OBJECT_CREATED: _f_object_created,
    EventType.OBJECT_MUTATED: _f_object_mutated,
    EventType.OBJECT_FREED: _f_object_freed,
    EventType.FUNCTION_ENTERED: _f_function_entered,
    EventType.FUNCTION_RETURNED: _f_function_returned,
    EventType.FUNCTION_EXITED: _f_function_exited,
    EventType.LOOP_STARTED: _f_loop_started,
    EventType.LOOP_ITERATION: _f_loop_iteration,
    EventType.LOOP_FINISHED: _f_loop_finished,
    EventType.EXCEPTION_RAISED: _f_exception_raised,
    EventType.EXCEPTION_HANDLED: _f_exception_handled,
    EventType.ALGORITHM_EVENT: _f_algorithm,
    EventType.COLLECTION_CREATED: _noop,
}

_INVERSE: dict[EventType, Handler] = {
    EventType.PROGRAM_STARTED: _i_program_started,
    EventType.PROGRAM_FINISHED: _i_program_finished,
    EventType.BUDGET_EXCEEDED: _i_budget_exceeded,
    EventType.STDOUT_WRITE: _i_stdout,
    EventType.STDERR_WRITE: _i_stderr,
    EventType.VARIABLE_CREATED: _i_var_created,
    EventType.VARIABLE_WRITTEN: _i_var_written,
    EventType.VARIABLE_DELETED: _i_var_deleted,
    EventType.SUBSCRIPT_WRITTEN: _i_subscript_written,
    EventType.SUBSCRIPT_DELETED: _i_subscript_deleted,
    EventType.ATTRIBUTE_WRITTEN: _i_attribute_written,
    EventType.OBJECT_CREATED: _i_object_created,
    EventType.OBJECT_MUTATED: _i_object_mutated,
    EventType.OBJECT_FREED: _i_object_freed,
    EventType.FUNCTION_ENTERED: _i_function_entered,
    EventType.FUNCTION_RETURNED: _i_function_returned,
    EventType.FUNCTION_EXITED: _i_function_exited,
    EventType.LOOP_STARTED: _i_loop_started,
    EventType.LOOP_ITERATION: _i_loop_iteration,
    EventType.LOOP_FINISHED: _i_loop_finished,
    EventType.EXCEPTION_RAISED: _i_exception_raised,
    EventType.EXCEPTION_HANDLED: _i_exception_handled,
    EventType.ALGORITHM_EVENT: _i_algorithm,
    EventType.COLLECTION_CREATED: _noop,
}


def mutating_types() -> set[EventType]:
    """Types with a forward handler -- used by the reducer-coverage test."""
    return set(_FORWARD) | set(_INVERSE)
