"""The built-in lifters.

Each one is a small state machine over generic events.  Read the precision
notes: a lifter that invents an operation is worse than one that misses it,
because an invented ``SWAP`` is a lie about the program.  Thresholds are
therefore set to favour precision over recall, and every negative case in
``tests/unit/test_lifters.py`` asserts that a near-miss does *not* fire.
"""

from __future__ import annotations

from typing import Any

from ..core.events import Event, EventType
from ..core.values import same_value, scalar_of
from .base import LiftContext, Lifter, algorithm_event


class SwapLifter:
    """Two subscript writes on one container that exchange their values.

    Matches every spelling: the tuple form ``a[i], a[j] = a[j], a[i]``, the
    temp-variable form, and separate statements -- because it looks at the
    *values written*, not at the syntax.  Requires the same container, the same
    frame, distinct indices, and ``new_i == old_j and new_j == old_i``.
    """

    id = "swap"

    def __init__(self, span: int = 6) -> None:
        self.span = span
        self._pending: dict[tuple[int, str], tuple[int, Event]] = {}

    def reset(self) -> None:
        self._pending.clear()

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type is not EventType.SUBSCRIPT_WRITTEN:
            return []
        ref = ev.payload.get("container_ref")
        if not ref:
            return []
        key = (ev.frame, ref)
        previous = self._pending.get(key)
        self._pending[key] = (ev.id, ev)
        if previous is None:
            return []
        first_id, first = previous
        if ev.id - first_id > self.span:
            return []
        i, j = first.payload.get("index"), ev.payload.get("index")
        if not isinstance(i, int) or not isinstance(j, int) or i == j:
            return []
        if not (
            same_value(first.payload.get("new"), ev.payload.get("old"))
            and same_value(ev.payload.get("new"), first.payload.get("old"))
        ):
            return []
        del self._pending[key]
        return [
            algorithm_event(
                "swap",
                {
                    "i": i, "j": j,
                    "a": ev.payload.get("new"),
                    "b": first.payload.get("new"),
                    "name": ctx.names.get(ref),
                },
                ev, self.id, confidence=0.95, ref=ref,
            )
        ]


class CompareLifter:
    """A comparison whose operands both came from the same container.

    ``arr[j] > arr[j+1]`` is the canonical case.  Requires both operand values
    to match the values of subscript reads on one container within the same
    statement, which is what distinguishes an element comparison from an
    ordinary numeric one.
    """

    id = "compare"

    def __init__(self, span: int = 8) -> None:
        self.span = span

    def reset(self) -> None:
        return None

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type is not EventType.EXPRESSION_EVALUATED:
            return []
        if ev.payload.get("kind") != "compare":
            return []
        operands = ev.payload.get("operands") or []
        if len(operands) != 2:
            return []
        reads: list[Event] = [
            e for e in ctx.recent(self.span)
            if e.type is EventType.SUBSCRIPT_READ and ev.id - e.id <= self.span
        ]
        left = _match_read(reads, operands[0])
        # Exclude the event already matched: without this, `arr[mid] == target`
        # where both happen to be 11 would match the same read twice and report
        # a two-element comparison that never occurred.
        right = _match_read([e for e in reads if e is not left], operands[1])
        if left is None and right is None:
            return []
        if left is not None and right is not None:
            same_container = (
                left.payload.get("container_ref") == right.payload.get("container_ref")
            )
            confidence = 0.85 if same_container else 0.8   # e.g. left[i] vs right[j]
        else:
            confidence = 0.75   # element compared against a plain value
        anchor = left or right
        ref = anchor.payload.get("container_ref")
        return [
            algorithm_event(
                "compare",
                {
                    "i": left.payload.get("index") if left is not None else None,
                    "j": right.payload.get("index") if right is not None else None,
                    "a": operands[0],
                    "b": operands[1],
                    "op": ev.payload.get("op"),
                    "result": scalar_of(ev.payload.get("value")),
                    "name": ctx.names.get(ref or ""),
                    "ref_j": (
                        right.payload.get("container_ref") if right is not None else None
                    ),
                },
                ev, self.id, confidence=confidence, ref=ref,
            )
        ]


class PointerLifter:
    """An integer variable used as an index into a container.

    Produces the ``lo``/``hi``/``mid``/``i``/``j`` carets under an array view.
    Fires when a variable's current value is used as a subscript index on the
    same container within a short window -- which is exactly what makes a
    variable a *pointer* rather than just a number.
    """

    id = "pointer"

    def __init__(self, span: int = 4) -> None:
        self.span = span
        self._values: dict[tuple[int, str], Any] = {}
        self._emitted: dict[tuple[int, str, str], int] = {}

    def reset(self) -> None:
        self._values.clear()
        self._emitted.clear()

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type in (EventType.VARIABLE_WRITTEN, EventType.VARIABLE_CREATED):
            value = ev.payload.get("new") or ev.payload.get("value")
            scalar = scalar_of(value)
            if isinstance(scalar, int) and not isinstance(scalar, bool):
                self._values[(ev.frame, ev.payload["name"])] = scalar
            return []
        if ev.type not in (EventType.SUBSCRIPT_READ, EventType.SUBSCRIPT_WRITTEN):
            return []
        index = ev.payload.get("index")
        ref = ev.payload.get("container_ref")
        if not isinstance(index, int) or isinstance(index, bool) or not ref:
            return []
        out: list[Event] = []
        for (frame, name), value in self._values.items():
            if frame != ev.frame or value != index:
                continue
            key = (ev.frame, ref, name)
            if self._emitted.get(key) == index:
                continue
            self._emitted[key] = index
            out.append(
                algorithm_event(
                    "pointer",
                    {"index": index, "label": name, "name": ctx.names.get(ref)},
                    ev, self.id, confidence=0.7, ref=ref,
                )
            )
        return out


class StackQueueLifter:
    """Container mutations that read as stack or queue operations.

    Driven by ``OBJECT_MUTATED.op``, so it works for ``list.append``/``pop``,
    ``deque.append``/``popleft`` and ``heapq.heappush``/``heappop`` alike.
    """

    id = "stackqueue"

    #: (container tag, method) -> semantic name.  The container's structure
    #: decides the vocabulary: appending to a deque is an enqueue, appending to
    #: a list is a push, and adding to a set is neither (VisitLifter covers it).
    PUSH = {"append": "push", "appendleft": "enqueue",
            "heapq.heappush": "enqueue", "heappush": "enqueue", "insort": "enqueue"}
    POP = {"pop": "pop", "popleft": "dequeue", "heapq.heappop": "dequeue",
           "heappop": "dequeue"}
    QUEUE_TAGS = ("deque",)

    def reset(self) -> None:
        return None

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type is not EventType.OBJECT_MUTATED:
            return []
        op = str(ev.payload.get("op", ""))
        base = op.split(".")[-1]
        ref = ev.payload.get("ref")
        before = ev.payload.get("before") or {}
        after = ev.payload.get("after") or {}
        before_items = before.get("items") or []
        after_items = after.get("items") or []

        tag = after.get("t") or before.get("t")
        if tag in ("set", "frozenset"):
            return []
        queue_like = tag in self.QUEUE_TAGS

        if base in self.PUSH and len(after_items) > len(before_items):
            name = "enqueue" if queue_like else self.PUSH[base]
            value = _added_item(before_items, after_items)
            return [
                algorithm_event(
                    name,
                    {"value": value, "length": len(after_items),
                     "name": ctx.names.get(ref or "")},
                    ev, self.id, confidence=0.9, ref=ref,
                )
            ]
        if base in self.POP and len(after_items) < len(before_items):
            name = "dequeue" if queue_like else self.POP[base]
            value = _removed_item(before_items, after_items)
            return [
                algorithm_event(
                    name,
                    {"value": value, "length": len(after_items),
                     "name": ctx.names.get(ref or "")},
                    ev, self.id, confidence=0.9, ref=ref,
                )
            ]
        return []


class RelaxLifter:
    """A conditional improvement of a keyed distance.

    Not a Dijkstra detector: it fires on any write ``d[v] = candidate`` guarded
    by a comparison whose right operand was the previous ``d[v]`` and whose
    result was true.  Bellman-Ford, Floyd-Warshall's inner loop, and a
    dynamic-programming ``best[i] = min(...)`` all match, which is the point.
    """

    id = "relax"

    def __init__(self, span: int = 10) -> None:
        self.span = span

    def reset(self) -> None:
        return None

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type is not EventType.SUBSCRIPT_WRITTEN:
            return []
        old, new = ev.payload.get("old"), ev.payload.get("new")
        old_scalar, new_scalar = scalar_of(old), scalar_of(new)
        if not _is_number(old_scalar) or not _is_number(new_scalar):
            return []
        if new_scalar >= old_scalar:
            return []
        guard = None
        for e in reversed(ctx.recent(self.span)):
            if e.type is EventType.EXPRESSION_EVALUATED and e.payload.get("kind") == "compare":
                operands = e.payload.get("operands") or []
                if len(operands) == 2 and (
                    same_value(operands[1], old) or same_value(operands[0], new)
                ):
                    guard = e
                    break
        if guard is None:
            return []
        return [
            algorithm_event(
                "relax",
                {
                    "v": ev.payload.get("index"),
                    "old": old_scalar,
                    "new": new_scalar,
                    "improved": True,
                    "name": ctx.names.get(ev.payload.get("container_ref") or ""),
                },
                ev, self.id, confidence=0.65,
                ref=ev.payload.get("container_ref"),
            )
        ]


class VisitLifter:
    """Insertion into a set that is keyed by graph-like node identifiers.

    Requires the added element to also appear as a key of some dict currently on
    the heap -- the structural signal that it names a node rather than being an
    arbitrary value.
    """

    id = "visit"

    def reset(self) -> None:
        return None

    def feed(self, ev: Event, ctx: LiftContext) -> list[Event]:
        if ev.type is not EventType.OBJECT_MUTATED:
            return []
        if str(ev.payload.get("op", "")).split(".")[-1] != "add":
            return []
        after = ev.payload.get("after") or {}
        if after.get("t") not in ("set", "frozenset"):
            return []
        before_items = (ev.payload.get("before") or {}).get("items") or []
        value = _added_item(before_items, after.get("items") or [])
        if value is None or not _is_node_key(value, ctx):
            return []
        return [
            algorithm_event(
                "visit",
                {"node": value, "name": ctx.names.get(ev.payload.get("ref") or "")},
                ev, self.id, confidence=0.7, ref=ev.payload.get("ref"),
            )
        ]


# ----------------------------------------------------------------------
def _match_read(reads: list[Event], operand: Any) -> Event | None:
    for e in reversed(reads):
        if same_value(e.payload.get("value"), operand):
            return e
    return None


def _added_item(before: list[Any], after: list[Any]) -> Any:
    seen = list(before)
    for item in after:
        for i, existing in enumerate(seen):
            if same_value(existing, item):
                del seen[i]
                break
        else:
            return item
    return after[-1] if after else None


def _removed_item(before: list[Any], after: list[Any]) -> Any:
    seen = list(after)
    for item in before:
        for i, existing in enumerate(seen):
            if same_value(existing, item):
                del seen[i]
                break
        else:
            return item
    return before[-1] if before else None


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_node_key(value: Any, ctx: LiftContext) -> bool:
    for record in ctx.heap.values():
        if record.get("t") not in ("dict", "defaultdict", "OrderedDict"):
            continue
        for pair in record.get("entries") or []:
            if same_value(pair[0], value):
                return True
    return False


DEFAULT_LIFTERS: list[type[Lifter]] = [
    SwapLifter, CompareLifter, PointerLifter, StackQueueLifter,
    RelaxLifter, VisitLifter,
]
