"""The probe API called by instrumented code.

Every ``_as_*`` function here corresponds to a rewrite rule in
``languages/python/transformer.py`` (see docs/05-python-execution-strategy.md
section K.4).  Two invariants govern this module:

1. **Probes must not change program semantics.**  They return exactly the value
   the original expression would have produced, they evaluate their operands
   exactly once, and they never swallow exceptions.
2. **Probes must be cheap.**  They run in the hot path; the recorder is a module
   global rather than a lookup, values are encoded lazily, and containers are
   re-snapshotted only when a mutation was actually observed.
"""

from __future__ import annotations

import operator
import sys
from typing import Any, Iterable, Iterator

from ..core.events import EventType
from ..core.values import MAPPING_TAGS, SEQUENCE_TAGS, SET_TAGS, _type_tag, same_value
from .recorder import Recorder

# ---------------------------------------------------------------------------
# module state
# ---------------------------------------------------------------------------
_R: Recorder = None  # type: ignore[assignment]
_SHADOW: dict[tuple[int, str], Any] = {}
_SKIPPED: set[tuple[int, str]] = set()


class _Missing:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()


def install(recorder: Recorder) -> dict[str, Any]:
    """Bind the recorder and return the namespace injected into user globals."""
    global _R
    _R = recorder
    _SHADOW.clear()
    _SKIPPED.clear()
    return {name: obj for name, obj in globals().items() if name.startswith("_as_")}


# ---------------------------------------------------------------------------
# frame / scope helpers
# ---------------------------------------------------------------------------
def _lookup(name: str, back: int = 2) -> tuple[Any, str]:
    """Current binding of ``name`` in the calling user frame, plus its scope."""
    f = sys._getframe(back)
    loc = f.f_locals
    glb = f.f_globals
    if loc is glb:
        return (glb[name], "global") if name in glb else (MISSING, "global")
    if name in loc:
        return loc[name], "local"
    if name in glb:
        return glb[name], "global"
    return MISSING, "local"


def _shadow_key(name: str) -> tuple[int, str]:
    return (_R.frame_id, name)


def _remember(name: str, encoded: Any) -> None:
    _SHADOW[_shadow_key(name)] = encoded


# ---------------------------------------------------------------------------
# lines, skips
# ---------------------------------------------------------------------------
def _as_line(line: int) -> None:
    _R.emit(EventType.LINE_EXECUTED, None, line)


def _as_skip(reason: str, construct: str, line: int) -> None:
    key = (line, construct)
    if key in _SKIPPED:
        return
    _SKIPPED.add(key)
    _R.emit(
        EventType.INSTRUMENTATION_SKIPPED,
        {"reason": reason, "construct": construct},
        line,
    )


# ---------------------------------------------------------------------------
# variables
# ---------------------------------------------------------------------------
def _as_store(name: str, value: Any, line: int) -> Any:
    """``x = _as_store('x', <expr>, line)`` -- returns ``value`` unchanged."""
    old, scope = _lookup(name)
    new_enc = _R.enc(value)
    _R.ref_name(value, name)
    if old is MISSING:
        _R.emit(
            EventType.VARIABLE_CREATED,
            {"name": name, "scope": scope, "value": new_enc},
            line,
        )
    else:
        old_enc = _SHADOW.get(_shadow_key(name))
        if old_enc is None:
            old_enc = _R.enc(old)
        _R.emit(
            EventType.VARIABLE_WRITTEN,
            {"name": name, "scope": scope, "old": old_enc, "new": new_enc},
            line,
        )
    _remember(name, new_enc)
    return value


def _as_load(name: str, value: Any, line: int) -> Any:
    _R.emit(
        EventType.VARIABLE_READ,
        {"name": name, "scope": "local", "value": _R.enc(value)},
        line,
    )
    return value


def _as_del_name(name: str, line: int) -> None:
    old, scope = _lookup(name)
    if old is MISSING:
        return
    _R.emit(
        EventType.VARIABLE_DELETED,
        {"name": name, "scope": scope, "old": _R.enc(old)},
        line,
    )
    _SHADOW.pop(_shadow_key(name), None)


def _as_unpack(value: Any, n: int, line: int) -> tuple:
    """Materialise an unpacking RHS so each target can be assigned by a probe.

    Used when a tuple target contains a subscript or attribute -- the case that
    makes ``arr[i], arr[j] = arr[j], arr[i]`` observable.  Raises the same
    ValueError CPython would for a length mismatch.
    """
    items = tuple(value)
    if len(items) != n:
        if len(items) < n:
            raise ValueError(
                f"not enough values to unpack (expected {n}, got {len(items)})"
            )
        raise ValueError(f"too many values to unpack (expected {n})")
    return items


def _as_sync(names: tuple[str, ...], line: int) -> None:
    """Post-statement reconciliation for targets we could not model precisely.

    Used for starred/nested unpacking and any construct the transformer declined
    to rewrite finely.  Values are read back from the frame, so they are exact;
    only the sub-statement detail is lost.
    """
    for name in names:
        value, scope = _lookup(name)
        if value is MISSING:
            continue
        enc = _R.enc(value)
        key = _shadow_key(name)
        prev = _SHADOW.get(key)
        if prev is None:
            _R.ref_name(value, name)
            _R.emit(
                EventType.VARIABLE_CREATED,
                {"name": name, "scope": scope, "value": enc},
                line,
            )
        elif not same_value(prev, enc):
            _R.emit(
                EventType.VARIABLE_WRITTEN,
                {"name": name, "scope": scope, "old": prev, "new": enc},
                line,
            )
        _SHADOW[key] = enc


# ---------------------------------------------------------------------------
# subscripts and attributes
# ---------------------------------------------------------------------------
def _enc_index(index: Any) -> Any:
    if isinstance(index, (int, str, float, bool)) and not isinstance(index, bool):
        return index
    if isinstance(index, bool):
        return index
    if isinstance(index, slice):
        return f"{_s(index.start)}:{_s(index.stop)}{':' + _s(index.step) if index.step is not None else ''}"
    try:
        return repr(index)[:60]
    except Exception:  # pragma: no cover
        return "<index>"


def _s(v: Any) -> str:
    return "" if v is None else str(v)


def _as_sub_get(container: Any, index: Any, line: int) -> Any:
    value = container[index]
    ref = _R.enc(container)
    _R.emit(
        EventType.SUBSCRIPT_READ,
        {
            "container_ref": ref.get("r"),
            "container_name": _R.name_for(container),
            "index": _enc_index(index),
            "value": _R.enc(value),
        },
        line,
    )
    _R.bump("array_reads")
    return value


def _as_sub_set(value: Any, container: Any, index: Any, line: int) -> Any:
    """``a[i] = v`` -- argument order (value, container, index) mirrors CPython's
    evaluation order for a subscript assignment."""
    existed = True
    try:
        old = container[index]
    except Exception:
        old = MISSING
        existed = False
    ref = _R.enc(container)

    if isinstance(index, slice):
        before = _R.encoder.snapshot(container)
        container[index] = value
        after = _R.encoder.snapshot(container)
        _R.emit(
            EventType.OBJECT_MUTATED,
            {
                "ref": ref.get("r"),
                "name": _R.name_for(container),
                "op": "__setitem__",
                "before": before,
                "after": after,
            },
            line,
        )
        return value

    container[index] = value
    _R.encoder.snapshot(container)
    _R.emit(
        EventType.SUBSCRIPT_WRITTEN,
        {
            "container_ref": ref.get("r"),
            "container_name": _R.name_for(container),
            "index": _enc_index(index),
            "old": None if old is MISSING else _R.enc(old),
            "new": _R.enc(value),
            "existed": existed,
        },
        line,
    )
    _R.bump("array_writes")
    return value


def _as_sub_aug(op: str, container: Any, index: Any, value: Any, line: int) -> Any:
    """``a[i] op= v`` with a single evaluation of ``a`` and ``i``."""
    old = container[index]
    new = _INPLACE[op](old, value)
    return _as_sub_set(new, container, index, line)


def _as_attr_aug(op: str, obj: Any, name: str, value: Any, line: int) -> Any:
    """``o.f op= v`` with a single evaluation of ``o``."""
    old = getattr(obj, name)
    return _as_attr_set(_INPLACE[op](old, value), obj, name, line)


def _as_sub_del(container: Any, index: Any, line: int) -> None:
    old = container[index]
    position = None
    if isinstance(container, (list, tuple)) and isinstance(index, int):
        position = index if index >= 0 else len(container) + index
    elif hasattr(container, "keys"):
        # Dicts preserve insertion order, so undoing a delete has to put the
        # key back where it was, not at the end.
        for i, key in enumerate(container.keys()):
            if key == index:
                position = i
                break
    ref = _R.enc(container)
    del container[index]
    _R.encoder.snapshot(container)
    _R.emit(
        EventType.SUBSCRIPT_DELETED,
        {
            "container_ref": ref.get("r"),
            "container_name": _R.name_for(container),
            "index": _enc_index(index),
            "old": _R.enc(old),
            "position": position,
        },
        line,
    )


def _as_attr_get(obj: Any, name: str, line: int) -> Any:
    value = getattr(obj, name)
    ref = _R.enc(obj)
    if ref.get("k") == "ref":
        _R.emit(
            EventType.ATTRIBUTE_READ,
            {"object_ref": ref.get("r"), "name": name, "value": _R.enc(value)},
            line,
        )
    return value


def _as_attr_set(value: Any, obj: Any, name: str, line: int) -> Any:
    existed = hasattr(obj, name)
    old = getattr(obj, name, MISSING)
    ref = _R.enc(obj)
    setattr(obj, name, value)
    if ref.get("k") == "ref":
        _R.encoder.snapshot(obj)
        _R.emit(
            EventType.ATTRIBUTE_WRITTEN,
            {
                "object_ref": ref.get("r"),
                "name": name,
                "old": None if old is MISSING else _R.enc(old),
                "new": _R.enc(value),
                "existed": existed,
            },
            line,
        )
    return value


# ---------------------------------------------------------------------------
# expressions
# ---------------------------------------------------------------------------
_BINOPS = {
    "+": operator.add, "-": operator.sub, "*": operator.mul,
    "/": operator.truediv, "//": operator.floordiv, "%": operator.mod,
    "**": operator.pow, "<<": operator.lshift, ">>": operator.rshift,
    "|": operator.or_, "&": operator.and_, "^": operator.xor,
    "@": operator.matmul,
}
_INPLACE = {
    "+": operator.iadd, "-": operator.isub, "*": operator.imul,
    "/": operator.itruediv, "//": operator.ifloordiv, "%": operator.imod,
    "**": operator.ipow, "<<": operator.ilshift, ">>": operator.irshift,
    "|": operator.ior, "&": operator.iand, "^": operator.ixor,
    "@": operator.imatmul,
}
_CMPOPS = {
    "<": operator.lt, "<=": operator.le, ">": operator.gt, ">=": operator.ge,
    "==": operator.eq, "!=": operator.ne,
    "is": operator.is_, "is not": operator.is_not,
    "in": lambda a, b: a in b, "not in": lambda a, b: a not in b,
}


def _as_binop(op: str, a: Any, b: Any, line: int) -> Any:
    result = _BINOPS[op](a, b)
    _R.emit(
        EventType.EXPRESSION_EVALUATED,
        {"op": op, "operands": [_R.enc(a), _R.enc(b)], "value": _R.enc(result)},
        line,
    )
    return result


def _as_inplace(op: str, a: Any, b: Any, line: int) -> Any:
    result = _INPLACE[op](a, b)
    _R.emit(
        EventType.EXPRESSION_EVALUATED,
        {
            "op": op + "=",
            "operands": [_R.enc(a), _R.enc(b)],
            "value": _R.enc(result),
        },
        line,
    )
    if result is a and _R.encoder.known(a):
        _note_container_mutation(a, op + "=", line)
    return result


def _as_compare(op: str, a: Any, b: Any, line: int) -> Any:
    result = _CMPOPS[op](a, b)
    _R.emit(
        EventType.EXPRESSION_EVALUATED,
        {
            "op": op,
            "kind": "compare",
            "operands": [_R.enc(a), _R.enc(b)],
            "value": _R.enc(result),
        },
        line,
    )
    _R.bump("comparisons")
    return result


def _as_value(value: Any, line: int, expr: str = "") -> Any:
    _R.emit(
        EventType.EXPRESSION_EVALUATED,
        {"expr": expr, "value": _R.enc(value)},
        line,
    )
    return value


def _as_cond(value: Any, kind: str, line: int, expr: str = "") -> bool:
    """Evaluate a branch condition once and record its truth value.

    Returns ``bool(value)`` rather than ``value``: ``if``/``while`` take the
    truthiness anyway, and returning the already-computed bool avoids invoking
    a user-defined ``__bool__`` twice.
    """
    result = bool(value)
    _R.emit(
        EventType.CONDITION_EVALUATED,
        {
            "kind": kind,
            "result": result,
            "expr": expr,
            "operands": [_R.enc(value)] if not isinstance(value, bool) else [],
        },
        line,
    )
    return result


def _as_branch(branch: str, line: int) -> None:
    _R.emit(EventType.BRANCH_TAKEN, {"branch": branch}, line)


# ---------------------------------------------------------------------------
# loops
# ---------------------------------------------------------------------------
def _as_loop_enter(loop_id: str, kind: str, line: int) -> None:
    _R.loop_counters[loop_id] = 0
    _R.counters.setdefault("loop_iterations", 0)
    _R.emit(EventType.LOOP_STARTED, {"loop_id": loop_id, "kind": kind}, line)
    _LOOP_EXIT[loop_id] = "normal"


_LOOP_EXIT: dict[str, str] = {}


def _as_iter(loop_id: str, iterable: Iterable[Any], line: int, var: str = "") -> Iterator[Any]:
    """Wrap a ``for`` iterable, emitting one event per iteration.

    A generator, so laziness is preserved: an infinite iterable stays infinite
    and is stopped by the budget guard rather than by materialization.
    """
    it = iter(iterable)
    while True:
        try:
            value = next(it)
        except StopIteration:
            return
        i = _R.loop_counters.get(loop_id, 0)
        _R.loop_counters[loop_id] = i + 1
        _R.bump("loop_iterations")
        _R.emit(
            EventType.LOOP_ITERATION,
            {
                "loop_id": loop_id,
                "iteration": i,
                "var": var or None,
                "value": _R.enc(value),
            },
            line,
        )
        yield value


def _as_loop_iter(loop_id: str, line: int) -> None:
    i = _R.loop_counters.get(loop_id, 0)
    _R.loop_counters[loop_id] = i + 1
    _R.bump("loop_iterations")
    _R.emit(EventType.LOOP_ITERATION, {"loop_id": loop_id, "iteration": i}, line)


def _as_loop_break(loop_id: str, line: int) -> None:
    _LOOP_EXIT[loop_id] = "break"


def _as_loop_exit(loop_id: str, line: int) -> None:
    reason = _LOOP_EXIT.pop(loop_id, "normal")
    if reason == "normal" and sys.exc_info()[0] is not None:
        reason = "exception"
    _R.emit(
        EventType.LOOP_FINISHED,
        {
            "loop_id": loop_id,
            "iterations": _R.loop_counters.get(loop_id, 0),
            "exit": reason,
        },
        line,
    )


# ---------------------------------------------------------------------------
# functions
# ---------------------------------------------------------------------------
def _as_enter(name: str, func_id: str, args: dict[str, Any], line: int) -> None:
    caller = _R.frame_id
    call_line = _R.current_line
    fid = _R.push_frame(func_id, name, call_line)
    encoded = {}
    for k, v in args.items():
        e = _R.enc(v)
        encoded[k] = e
        _SHADOW[(fid, k)] = e
        _R.ref_name(v, k)
    _R.bump("function_calls")
    _R.emit(
        EventType.FUNCTION_ENTERED,
        {
            "func_id": func_id,
            "name": name,
            "qualname": name,
            "args": encoded,
            "caller_frame": caller,
            "call_line": call_line,
        },
        line,
    )


def _as_return(value: Any, func_id: str, line: int) -> Any:
    _R.emit(
        EventType.FUNCTION_RETURNED,
        {"func_id": func_id, "value": _R.enc(value)},
        line,
    )
    return value


def _as_exit(func_id: str, line: int) -> None:
    reason = "exception" if sys.exc_info()[0] is not None else "return"
    frame = _R.frames[-1] if _R.frames else None
    name = frame.name if frame else ""
    fid = frame.frame_id if frame else 0
    _R.emit(
        EventType.FUNCTION_EXITED,
        {"func_id": func_id, "name": name, "reason": reason},
        line,
    )
    for key in [k for k in _SHADOW if k[0] == fid]:
        del _SHADOW[key]
    _R.pop_frame(func_id)


# ---------------------------------------------------------------------------
# method calls / container mutation
# ---------------------------------------------------------------------------
#: Structural tags whose mutation we observe by snapshotting.  Derived from the
#: encoder's tagging so that a user class named ``Counter`` is an object, not a
#: mapping -- matching on the bare type name got this wrong.
_CONTAINER_TAGS = SEQUENCE_TAGS | MAPPING_TAGS | SET_TAGS

_MUTATORS = {
    "append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",
    "add", "discard", "update", "popitem", "setdefault", "appendleft",
    "popleft", "extendleft", "rotate", "difference_update",
    "intersection_update", "symmetric_difference_update", "subtract",
}
_PURE = {
    "index", "count", "copy", "get", "keys", "values", "items", "fromkeys",
    "union", "intersection", "difference", "symmetric_difference", "issubset",
    "issuperset", "isdisjoint", "most_common", "elements", "join", "split",
    "strip", "lower", "upper", "format", "startswith", "endswith", "replace",
    "find", "rfind", "encode", "decode", "isdigit", "isalpha", "title",
}
#: Module-level functions that mutate their first argument in place.
_MODULE_MUTATORS = {
    "heappush", "heappop", "heapify", "heappushpop", "heapreplace",
    "shuffle", "insort", "insort_left", "insort_right",
}
#: Method name -> (structural event, direction)
_STRUCTURAL = {
    "append": (EventType.STACK_PUSH, "in"),
    "appendleft": (EventType.QUEUE_ENQUEUE, "in"),
    "pop": (EventType.STACK_POP, "out"),
    "popleft": (EventType.QUEUE_DEQUEUE, "out"),
    "add": (EventType.STACK_PUSH, "in"),
}


def _as_method(obj: Any, name: str, line: int, /, *args: Any, **kwargs: Any) -> Any:
    """Intercept ``obj.name(*args)``.

    This is what makes C-level mutation visible: ``arr.sort()``,
    ``q.popleft()``, ``heapq.heappush(h, x)``.  Without it the state model would
    silently drift from reality.
    """
    method = getattr(obj, name)
    tag = _type_tag(obj)

    if tag in _CONTAINER_TAGS and name not in _PURE:
        before = _R.encoder.snapshot(obj)
        result = method(*args, **kwargs)
        after = _R.encoder.snapshot(obj)
        ref = _R.encoder.ref_for(obj)
        _R.emit(
            EventType.OBJECT_MUTATED,
            {
                "ref": ref,
                "name": _R.encoder.name_of(ref),
                "op": name,
                "args": [_R.enc(a) for a in args[:4]],
                "before": before,
                "after": after,
            },
            line,
        )
        _emit_structural(obj, ref, name, args, result, line)
        return result

    if type(obj).__name__ == "module" and name in _MODULE_MUTATORS and args:
        target = args[0]
        if _type_tag(target) in _CONTAINER_TAGS:
            _R.enc(target)
            before = _R.encoder.snapshot(target)
            result = method(*args, **kwargs)
            after = _R.encoder.snapshot(target)
            ref = _R.encoder.ref_for(target)
            _R.emit(
                EventType.OBJECT_MUTATED,
                {
                    "ref": ref,
                    "name": _R.encoder.name_of(ref),
                    "op": f"{getattr(obj, '__name__', '?')}.{name}",
                    "args": [_R.enc(a) for a in args[1:4]],
                    "before": before,
                    "after": after,
                },
                line,
            )
            _emit_structural(target, ref, name, args[1:], result, line)
            return result

    return method(*args, **kwargs)


def _emit_structural(obj: Any, ref: str, name: str, args: tuple, result: Any, line: int) -> None:
    spec = _STRUCTURAL.get(name) or _STRUCTURAL.get(name.replace("heap", ""))
    if name in ("heappush",):
        spec = (EventType.STACK_PUSH, "in")
    elif name in ("heappop",):
        spec = (EventType.STACK_POP, "out")
    if spec is None:
        return
    etype, direction = spec
    value = args[0] if (direction == "in" and args) else result
    _R.emit(
        etype,
        {"ref": ref, "value": _R.enc(value), "length": _len_of(obj)},
        line,
    )


def _note_container_mutation(obj: Any, op: str, line: int) -> None:
    before = _R.encoder.heap_record(_R.encoder.ref_for(obj))
    after = _R.encoder.snapshot(obj)
    _R.emit(
        EventType.OBJECT_MUTATED,
        {
            "ref": _R.encoder.ref_for(obj),
            "name": _R.name_for(obj),
            "op": op,
            "before": before,
            "after": after,
        },
        line,
    )


def _len_of(obj: Any) -> int:
    try:
        return len(obj)
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# exceptions
# ---------------------------------------------------------------------------
def _as_raise(exc: Any, line: int) -> Any:
    """``raise _as_raise(<exc>, line)`` -- records and returns the value unchanged.

    Accepts both an instance and a class, since ``raise ValueError`` is legal.
    """
    if isinstance(exc, type) and issubclass(exc, BaseException):
        name, message = exc.__name__, ""
    else:
        name, message = type(exc).__name__, str(exc)
    _R.emit(
        EventType.EXCEPTION_RAISED,
        {"exc_type": name, "message": message},
        line,
    )
    return exc


def _as_handle(exc: BaseException, line: int) -> BaseException:
    _R.emit(
        EventType.EXCEPTION_HANDLED,
        {"exc_type": type(exc).__name__, "message": str(exc), "handler_line": line},
        line,
    )
    return exc


def _as_handled(exc_type: str, line: int) -> None:
    """``except ValueError:`` with no bound name -- record the handler type."""
    _R.emit(
        EventType.EXCEPTION_HANDLED,
        {"exc_type": exc_type, "message": "", "handler_line": line},
        line,
    )
