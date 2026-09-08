"""The ``algo`` object: explicit algorithm-level annotation for user code.

This is mechanism 1 of the two-mechanism semantic design (docs/07 §M.3).  Any
program -- a packaged plugin or something a student typed -- may call these to
emit high-level events directly.  Mechanism 2 (lifting patterns out of the
generic event stream) covers code that does not.

Both mechanisms emit the *same* ``ALGORITHM_EVENT`` envelope, distinguished only
by ``meta.origin``, so views, analytics and the AI have exactly one code path.

Every method is also safe to call outside AlgoStudio: ``null`` is a no-op
implementation with identical signatures, so annotated sources stay plain,
runnable Python.
"""

from __future__ import annotations

from typing import Any, Sequence

from ..core.events import EventType
from .recorder import Recorder


class SemanticAPI:
    """Bound to a live recorder inside the sandbox."""

    __slots__ = ("_r",)

    def __init__(self, recorder: Recorder) -> None:
        self._r = recorder

    # -- internals ----------------------------------------------------------
    def _emit(self, name: str, args: dict[str, Any], ref: str | None = None) -> None:
        payload: dict[str, Any] = {"name": name, "args": args}
        if ref:
            payload["ref"] = ref
        self._r.emit(
            EventType.ALGORITHM_EVENT,
            payload,
            _caller_line(),
            meta={"origin": "semantic"},
        )
        self._r.bump(f"algo.{name}")

    def _ref(self, container: Any) -> str | None:
        enc = self._r.enc(container)
        return enc.get("r")

    # -- comparisons and ordering ------------------------------------------
    def compare(self, a: Any, b: Any) -> int:
        """Record a comparison and return -1, 0 or 1."""
        result = -1 if a < b else (0 if a == b else 1)
        self._emit(
            "compare",
            {"a": self._r.enc(a), "b": self._r.enc(b), "result": result},
        )
        self._r.bump("comparisons")
        return result

    def swap(self, seq: Sequence[Any], i: int, j: int) -> None:
        """Perform and record ``seq[i], seq[j] = seq[j], seq[i]``."""
        ref = self._ref(seq)
        seq[i], seq[j] = seq[j], seq[i]  # type: ignore[index]
        self._r.encoder.snapshot(seq)
        self._emit(
            "swap",
            {"i": i, "j": j, "a": self._r.enc(seq[i]), "b": self._r.enc(seq[j])},
            ref,
        )
        self._r.bump("swaps")

    def pivot(self, seq: Sequence[Any], index: int, label: str = "pivot") -> None:
        self._emit("pivot", {"index": index, "label": label}, self._ref(seq))

    def partition(self, seq: Sequence[Any], lo: int, hi: int, label: str = "") -> None:
        self._emit("partition", {"lo": lo, "hi": hi, "label": label}, self._ref(seq))

    def merge(self, seq: Sequence[Any], lo: int, mid: int, hi: int) -> None:
        self._emit("merge", {"lo": lo, "mid": mid, "hi": hi}, self._ref(seq))

    # -- graph / tree -------------------------------------------------------
    def visit(self, node: Any, **kw: Any) -> Any:
        self._emit("visit", {"node": self._r.enc(node), **_enc_kw(self._r, kw)})
        self._r.bump("nodes_visited")
        return node

    def discover(self, node: Any, via: Any = None) -> Any:
        self._emit(
            "discover",
            {"node": self._r.enc(node), "via": self._r.enc(via) if via is not None else None},
        )
        return node

    def relax(self, u: Any, v: Any, weight: Any, improved: bool) -> bool:
        self._emit(
            "relax",
            {
                "u": self._r.enc(u),
                "v": self._r.enc(v),
                "weight": self._r.enc(weight),
                "improved": bool(improved),
            },
        )
        self._r.bump("edges_relaxed")
        return improved

    # -- containers ---------------------------------------------------------
    def enqueue(self, q: Any, x: Any) -> Any:
        ref = self._ref(q)
        q.append(x)
        self._r.encoder.snapshot(q)
        self._emit("enqueue", {"value": self._r.enc(x), "length": _len(q)}, ref)
        return x

    def dequeue(self, q: Any) -> Any:
        ref = self._ref(q)
        x = q.popleft() if hasattr(q, "popleft") else q.pop(0)
        self._r.encoder.snapshot(q)
        self._emit("dequeue", {"value": self._r.enc(x), "length": _len(q)}, ref)
        return x

    def push(self, s: Any, x: Any) -> Any:
        ref = self._ref(s)
        s.append(x)
        self._r.encoder.snapshot(s)
        self._emit("push", {"value": self._r.enc(x), "length": _len(s)}, ref)
        return x

    def pop(self, s: Any) -> Any:
        ref = self._ref(s)
        x = s.pop()
        self._r.encoder.snapshot(s)
        self._emit("pop", {"value": self._r.enc(x), "length": _len(s)}, ref)
        return x

    # -- annotations --------------------------------------------------------
    def pointer(self, seq: Any, index: int, label: str, color: str = "") -> None:
        self._emit(
            "pointer",
            {"index": index, "label": label, "color": color},
            self._ref(seq),
        )

    def region(self, seq: Any, lo: int, hi: int, label: str = "", color: str = "") -> None:
        self._emit(
            "region",
            {"lo": lo, "hi": hi, "label": label, "color": color},
            self._ref(seq),
        )

    def mark(self, target: Any, label: str = "", color: str = "") -> Any:
        enc = self._r.enc(target)
        self._emit(
            "mark",
            {"target": enc, "label": label, "color": color},
            enc.get("r"),
        )
        return target

    def unmark(self, target: Any, label: str = "") -> Any:
        enc = self._r.enc(target)
        self._emit("unmark", {"target": enc, "label": label}, enc.get("r"))
        return target

    def highlight(self, seq: Any, index: int, color: str = "") -> None:
        self._emit("highlight", {"index": index, "color": color}, self._ref(seq))

    def note(self, text: str) -> None:
        self._emit("note", {"text": str(text)[:500]})

    def metric(self, name: str, delta: int = 1) -> int:
        total = self._r.bump(name, delta)
        self._emit("metric", {"name": name, "delta": delta, "total": total})
        return total


class NullSemanticAPI:
    """No-op implementation so annotated sources run as plain Python."""

    def compare(self, a: Any, b: Any) -> int:
        return -1 if a < b else (0 if a == b else 1)

    def swap(self, seq: Any, i: int, j: int) -> None:
        seq[i], seq[j] = seq[j], seq[i]

    def enqueue(self, q: Any, x: Any) -> Any:
        q.append(x)
        return x

    def dequeue(self, q: Any) -> Any:
        return q.popleft() if hasattr(q, "popleft") else q.pop(0)

    def push(self, s: Any, x: Any) -> Any:
        s.append(x)
        return x

    def pop(self, s: Any) -> Any:
        return s.pop()

    def visit(self, node: Any, **kw: Any) -> Any:
        return node

    def discover(self, node: Any, via: Any = None) -> Any:
        return node

    def relax(self, u: Any, v: Any, weight: Any, improved: bool) -> bool:
        return improved

    def mark(self, target: Any, label: str = "", color: str = "") -> Any:
        return target

    def unmark(self, target: Any, label: str = "") -> Any:
        return target

    def metric(self, name: str, delta: int = 1) -> int:
        return 0

    def __getattr__(self, _name: str) -> Any:
        return lambda *a, **k: None


#: Importable no-op instance for sources executed outside AlgoStudio.
null = NullSemanticAPI()


def _enc_kw(recorder: Recorder, kw: dict[str, Any]) -> dict[str, Any]:
    return {k: recorder.enc(v) for k, v in kw.items()}


def _len(obj: Any) -> int:
    try:
        return len(obj)
    except Exception:
        return 0


def _caller_line() -> int:
    """Line in *user* code that invoked an ``algo`` method."""
    import sys

    try:
        return sys._getframe(3).f_lineno
    except Exception:  # pragma: no cover
        return 0
