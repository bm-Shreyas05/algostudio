"""Bounded, JSON-safe encoding of runtime values.

Encoded values are plain dicts rather than dataclasses: they are created in the
hot path of the sandbox child (potentially hundreds of thousands of times) and
are serialized straight to JSON, so the indirection would be pure cost.

Shape (docs/02-event-model.md H.4)::

    {"k":"int","v":42}
    {"k":"str","v":"hi","len":2}
    {"k":"ref","r":"h7","t":"list","n":8}
    {"k":"opaque","t":"function","repr":"<function f>"}
    {"k":"cycle","r":"h3"}

Containers live in the heap and are referenced by a synthetic id; primitives are
inline.  Truncation is always explicit (``trunc: True``) so a view can never
mistake a clipped value for a complete one.
"""

from __future__ import annotations

from typing import Any

# Types encoded inline rather than as heap references.
_PRIMITIVE = (int, float, bool, str, bytes, complex, type(None))

# Container types we model structurally.
SEQUENCE_TAGS = {"list", "tuple", "deque", "array"}
MAPPING_TAGS = {"dict", "defaultdict", "OrderedDict", "Counter"}
SET_TAGS = {"set", "frozenset"}


class EncodingLimits:
    __slots__ = ("max_depth", "max_items", "max_str", "max_heap_objects")

    def __init__(
        self,
        max_depth: int = 6,
        max_items: int = 256,
        max_str: int = 512,
        max_heap_objects: int = 50_000,
    ) -> None:
        self.max_depth = max_depth
        self.max_items = max_items
        self.max_str = max_str
        self.max_heap_objects = max_heap_objects


# --------------------------------------------------------------------------
# constructors
# --------------------------------------------------------------------------
NONE: dict[str, Any] = {"k": "none"}


def enc_int(v: int) -> dict[str, Any]:
    return {"k": "int", "v": v}


def enc_float(v: float) -> dict[str, Any]:
    # inf/nan are not valid JSON; carry them as tagged strings.
    if v != v or v in (float("inf"), float("-inf")):
        return {"k": "float", "v": None, "special": repr(v)}
    return {"k": "float", "v": v}


def enc_bool(v: bool) -> dict[str, Any]:
    return {"k": "bool", "v": v}


def enc_str(v: str, limit: int = 512) -> dict[str, Any]:
    if len(v) > limit:
        return {"k": "str", "v": v[:limit], "len": len(v), "trunc": True}
    return {"k": "str", "v": v, "len": len(v)}


def enc_ref(ref: str, tag: str, n: int, trunc: bool = False) -> dict[str, Any]:
    d = {"k": "ref", "r": ref, "t": tag, "n": n}
    if trunc:
        d["trunc"] = True
    return d


def enc_opaque(obj: Any) -> dict[str, Any]:
    try:
        r = repr(obj)
    except Exception:  # pragma: no cover - hostile __repr__
        r = "<unrepresentable>"
    return {"k": "opaque", "t": type(obj).__name__, "repr": r[:120]}


def is_ref(value: Any) -> bool:
    return isinstance(value, dict) and value.get("k") == "ref"


def ref_of(value: Any) -> str | None:
    return value.get("r") if is_ref(value) else None


def scalar_of(value: Any) -> Any:
    """Best-effort recovery of a plain Python scalar from an encoded value.

    Used by lifters, shape detectors and the AI verifier, all of which reason
    about numbers and strings but never need to reconstruct containers.
    """
    if not isinstance(value, dict):
        return value
    k = value.get("k")
    if k == "none":
        return None
    if k in ("int", "float", "bool", "str"):
        raw = value.get("v")
        if raw is None and value.get("special"):
            # inf / -inf / nan are not representable in JSON, so the encoder
            # parks them in "special".  Returning None here made every numeric
            # lifter skip the single most interesting relaxation in a
            # shortest-path algorithm: the one that replaces infinity.
            try:
                return float(value["special"])
            except (TypeError, ValueError):
                return None
        return raw
    return None


def same_value(a: Any, b: Any) -> bool:
    """Structural equality for encoded values (refs compare by identity)."""
    if a is b:
        return True
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    ka, kb = a.get("k"), b.get("k")
    if ka != kb:
        return False
    if ka == "ref":
        return a.get("r") == b.get("r")
    if ka == "none":
        return True
    return a.get("v") == b.get("v")


# --------------------------------------------------------------------------
# encoder
# --------------------------------------------------------------------------
class ValueEncoder:
    """Encodes live Python objects, allocating heap refs for containers.

    The encoder keeps a *strong* reference to every object it has seen.  This
    prevents ``id()`` reuse after garbage collection, which would silently
    corrupt the heap model.  The cost -- objects are not collected during a run
    -- is bounded because the run itself is budget-bounded.
    """

    __slots__ = ("limits", "_refs", "_keepalive", "_counter", "_heap", "_new", "_names")

    def __init__(self, limits: EncodingLimits | None = None) -> None:
        self.limits = limits or EncodingLimits()
        self._refs: dict[int, str] = {}
        self._keepalive: list[Any] = []
        self._counter = 0
        self._heap: dict[str, dict[str, Any]] = {}
        self._new: list[str] = []
        self._names: dict[str, str] = {}

    # -- ref management -----------------------------------------------------
    def ref_for(self, obj: Any) -> str:
        key = id(obj)
        ref = self._refs.get(key)
        if ref is None:
            self._counter += 1
            ref = f"h{self._counter}"
            self._refs[key] = ref
            self._keepalive.append(obj)
        return ref

    def known(self, obj: Any) -> bool:
        return id(obj) in self._refs

    def name_ref(self, ref: str, name: str) -> None:
        """Remember a human-friendly name for a heap object (best effort)."""
        self._names.setdefault(ref, name)

    def name_of(self, ref: str) -> str | None:
        return self._names.get(ref)

    # -- encoding -----------------------------------------------------------
    def encode(self, obj: Any, depth: int = 0, refresh: bool = False) -> dict[str, Any]:
        """Encode ``obj``; containers are registered in the heap as a side effect.

        A container already in the heap is *not* re-snapshotted unless
        ``refresh`` is set.  This matters: without it, encoding ``arr`` on every
        subscript read would be O(len(arr)) per read.  Correctness is preserved
        because every observed mutation path (subscript write, attribute write,
        mutating method call) refreshes explicitly and emits a delta event.
        """
        t = type(obj)
        if obj is None:
            return NONE
        if t is bool:
            return enc_bool(obj)
        if t is int:
            return enc_int(obj)
        if t is float:
            return enc_float(obj)
        if t is str:
            return enc_str(obj, self.limits.max_str)
        if t is bytes or t is bytearray:
            return {"k": "opaque", "t": t.__name__, "repr": repr(obj)[:120]}
        if t is complex:
            return {"k": "opaque", "t": "complex", "repr": repr(obj)}

        tag = _type_tag(obj)
        if tag is None:
            return enc_opaque(obj)

        ref = self.ref_for(obj)
        if depth >= self.limits.max_depth:
            return enc_ref(ref, tag, _safe_len(obj), trunc=True)
        rec = self._heap.get(ref)
        if rec is None:
            # Install a placeholder *before* recursing so a self-referential
            # structure (a = []; a.append(a)) terminates: the recursive encode
            # sees the record and returns a plain ref back to the parent.
            self._heap[ref] = {"ref": ref, "t": tag, "n": _safe_len(obj)}
            self._new.append(ref)
            rec = self.snapshot(obj, ref=ref, tag=tag, depth=depth)
        elif refresh:
            rec = self.snapshot(obj, ref=ref, tag=tag, depth=depth)
        return enc_ref(ref, tag, rec.get("n", 0), trunc=rec.get("trunc", False))

    def snapshot(
        self,
        obj: Any,
        ref: str | None = None,
        tag: str | None = None,
        depth: int = 0,
    ) -> dict[str, Any]:
        """(Re)build the heap record for a container and return it."""
        ref = ref or self.ref_for(obj)
        tag = tag or _type_tag(obj) or "object"
        limits = self.limits
        rec: dict[str, Any] = {"ref": ref, "t": tag}

        if tag in SEQUENCE_TAGS:
            seq = list(obj)
            rec["n"] = len(seq)
            if len(seq) > limits.max_items:
                seq = seq[: limits.max_items]
                rec["trunc"] = True
            rec["items"] = [self.encode(x, depth + 1) for x in seq]
        elif tag in MAPPING_TAGS:
            items = list(obj.items())
            rec["n"] = len(items)
            if len(items) > limits.max_items:
                items = items[: limits.max_items]
                rec["trunc"] = True
            rec["entries"] = [
                [self.encode(k, depth + 1), self.encode(v, depth + 1)] for k, v in items
            ]
        elif tag in SET_TAGS:
            elems = list(obj)
            rec["n"] = len(elems)
            if len(elems) > limits.max_items:
                elems = elems[: limits.max_items]
                rec["trunc"] = True
            rec["items"] = [self.encode(x, depth + 1) for x in elems]
        elif tag == "str":  # pragma: no cover - strings never reach here
            rec["n"] = len(obj)
        else:  # user-defined object
            rec["cls"] = type(obj).__name__
            fields = _object_fields(obj)
            rec["n"] = len(fields)
            if len(fields) > limits.max_items:
                fields = dict(list(fields.items())[: limits.max_items])
                rec["trunc"] = True
            rec["fields"] = {k: self.encode(v, depth + 1) for k, v in fields.items()}

        self._heap[ref] = rec
        return rec

    # -- heap access --------------------------------------------------------
    def heap_record(self, ref: str) -> dict[str, Any] | None:
        return self._heap.get(ref)

    def take_new(self) -> list[tuple[str, dict[str, Any]]]:
        """Refs first seen since the last call, oldest first, with their records.

        The recorder turns these into ``OBJECT_CREATED`` events so that heap
        state on the server is derived purely from the event stream.
        """
        if not self._new:
            return []
        out = [(r, self._heap[r]) for r in self._new if r in self._heap]
        self._new.clear()
        return out

    @property
    def heap(self) -> dict[str, dict[str, Any]]:
        return self._heap

    @property
    def object_count(self) -> int:
        return self._counter


def _type_tag(obj: Any) -> str | None:
    """Structural tag for a container, or ``None`` if it is not one we model."""
    t = type(obj)
    name = t.__name__
    if t is list:
        return "list"
    if t is tuple:
        return "tuple"
    if t is dict:
        return "dict"
    if t is set:
        return "set"
    if t is frozenset:
        return "frozenset"
    # Match on identity, not just the name: a user class called Counter must
    # not be encoded as collections.Counter.  (Found by the differential test.)
    module = getattr(t, "__module__", "")
    if module in ("collections", "_collections"):
        if name in ("deque", "defaultdict", "OrderedDict", "Counter"):
            return name
    if module == "array" and name == "array":
        return "array"
    # user-defined objects with a normal instance dict / slots
    if hasattr(obj, "__dict__") or hasattr(obj, "__slots__"):
        if callable(obj) or isinstance(obj, type):
            return None
        mod = getattr(t, "__module__", "")
        if mod in ("builtins", "types", "functools", "itertools"):
            return None
        return "object"
    return None


def _object_fields(obj: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    d = getattr(obj, "__dict__", None)
    if isinstance(d, dict):
        fields.update(d)
    for slot in getattr(type(obj), "__slots__", ()) or ():
        if isinstance(slot, str) and hasattr(obj, slot):
            fields[slot] = getattr(obj, slot)
    return {k: v for k, v in fields.items() if not k.startswith("__")}


def _safe_len(obj: Any) -> int:
    try:
        return len(obj)
    except Exception:
        return len(_object_fields(obj))


# --------------------------------------------------------------------------
# heap helpers used by the server side (reducer, shapes, AI)
# --------------------------------------------------------------------------
def heap_items(rec: dict[str, Any]) -> list[Any]:
    return rec.get("items") or []


def heap_entries(rec: dict[str, Any]) -> list[list[Any]]:
    return rec.get("entries") or []


def heap_fields(rec: dict[str, Any]) -> dict[str, Any]:
    return rec.get("fields") or {}


def to_python(value: Any, heap: dict[str, dict[str, Any]], depth: int = 0) -> Any:
    """Reconstruct a plain Python value from an encoded value + heap.

    Lossy by design (truncation, opaque objects, cycles).  Used only where an
    approximation is acceptable: shape detection, analytics, AI context.
    """
    if depth > 8 or not isinstance(value, dict):
        return value
    k = value.get("k")
    if k == "none":
        return None
    if k in ("int", "float", "bool", "str"):
        return value.get("v")
    if k == "cycle":
        return f"<cycle {value.get('r')}>"
    if k == "opaque":
        return value.get("repr")
    if k == "ref":
        rec = heap.get(value.get("r", ""))
        if rec is None:
            return f"<{value.get('t')} {value.get('r')}>"
        t = rec.get("t")
        if t in SEQUENCE_TAGS:
            out = [to_python(x, heap, depth + 1) for x in heap_items(rec)]
            return tuple(out) if t == "tuple" else out
        if t in MAPPING_TAGS:
            return {
                _hashable(to_python(kk, heap, depth + 1)): to_python(vv, heap, depth + 1)
                for kk, vv in heap_entries(rec)
            }
        if t in SET_TAGS:
            return {_hashable(to_python(x, heap, depth + 1)) for x in heap_items(rec)}
        return {
            "__class__": rec.get("cls"),
            **{k2: to_python(v2, heap, depth + 1) for k2, v2 in heap_fields(rec).items()},
        }
    return value


def _hashable(x: Any) -> Any:
    if isinstance(x, (list, set)):
        return tuple(x)
    if isinstance(x, dict):
        return tuple(sorted(x.items(), key=lambda kv: str(kv[0])))
    return x
