"""Time travel: checkpoints plus invertible events.

Two mechanisms covering two different access patterns (docs/03 §I.3):

* **Invertible events** make single-step-backward O(1).  That is the
  interaction that matters most for learning ("wait, how did `high` become 3?"),
  so it gets the best complexity.
* **Checkpoints every K events** make an arbitrary seek O(K) regardless of how
  far into the execution it lands, which is what makes slider scrubbing smooth.

``seek`` picks between them with a cost model, so the same entry point handles
step-back (cost 1), a long scrub left (checkpoint), and a jump to the end.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from ..core.events import Event, EventType
from . import reducer
from .model import ExecutionState

DEFAULT_INTERVAL = 64
#: Total checkpoint budget; the interval widens for long executions so memory
#: stays bounded rather than growing with trace length.
MAX_CHECKPOINTS = 512


def normalize_ids(events: list[Event]) -> list[Event]:
    """Renumber so ``events[i].id == i``, and record what each event displaced.

    Renumbering is needed because lifting inserts synthesized events; dense ids
    let the reducer treat ``state.step`` as a list index, which makes checkpoint
    lookup a plain integer division.

    The second job is what makes inversion *local*.  Location is sticky -- not
    every event carries one -- so undoing an event has to know the line that was
    current before it.  Two short meta keys carry that:

    ``pl``   the current source line before this event
    ``pfl``  the line this event's own frame was on before it

    Without ``pfl``, undoing a FUNCTION_EXITED would leave the caller's frame
    showing the callee's last line instead of the call site.
    """
    current = 0
    frame_lines: dict[int, int] = {}
    for i, ev in enumerate(events):
        ev.id = i
        ev.step = i
        if current:
            ev.meta["pl"] = current
        prev_frame_line = frame_lines.get(ev.frame, 0)
        if prev_frame_line:
            ev.meta["pfl"] = prev_frame_line
        if ev.loc is not None:
            current = ev.loc.line
            frame_lines[ev.frame] = ev.loc.line
    return events


class Timeline:
    def __init__(self, events: Sequence[Event], checkpoint_interval: int | None = None):
        self.events = list(events)
        n = len(self.events)
        interval = checkpoint_interval or DEFAULT_INTERVAL
        if n // max(interval, 1) > MAX_CHECKPOINTS:
            interval = max(interval, n // MAX_CHECKPOINTS + 1)
        self.interval = max(1, interval)
        self._checkpoints: dict[int, ExecutionState] = {}
        self._built = False

    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.events)

    @property
    def last_step(self) -> int:
        return len(self.events) - 1

    def initial(self) -> ExecutionState:
        return ExecutionState()

    def _build(self) -> None:
        if self._built:
            return
        state = ExecutionState()
        self._checkpoints[-1] = state.clone()
        for i, ev in enumerate(self.events):
            reducer.apply(state, ev)
            if i % self.interval == 0:
                self._checkpoints[i] = state.clone()
        self._checkpoints[self.last_step] = state.clone()
        self._built = True

    def _nearest_checkpoint(self, step: int) -> tuple[int, ExecutionState]:
        self._build()
        index = (step // self.interval) * self.interval
        while index >= 0 and index not in self._checkpoints:
            index -= self.interval
        if index < 0 or index > step:
            return -1, self._checkpoints[-1]
        return index, self._checkpoints[index]

    # ------------------------------------------------------------------
    def state_at(self, step: int) -> ExecutionState:
        """State after applying ``events[0..step]``.  ``step == -1`` is initial."""
        step = max(-1, min(step, self.last_step))
        if step < 0:
            return self.initial()
        base_index, base = self._nearest_checkpoint(step)
        state = base.clone()
        for i in range(base_index + 1, step + 1):
            reducer.apply(state, self.events[i])
        return state

    def step_forward(self, state: ExecutionState) -> ExecutionState:
        nxt = state.step + 1
        if nxt > self.last_step:
            return state
        return reducer.apply(state, self.events[nxt])

    def step_back(self, state: ExecutionState) -> ExecutionState:
        """O(1): apply the inverse of the event that produced this state."""
        cur = state.step
        if cur < 0:
            return state
        return reducer.unapply(state, self.events[cur],
                               self.events[cur - 1] if cur >= 1 else None)

    def seek(self, state: ExecutionState, target: int) -> ExecutionState:
        target = max(-1, min(target, self.last_step))
        current = state.step
        if target == current:
            return state
        if target > current:
            # Forward from here is never worse than rebuilding from a checkpoint.
            for i in range(current + 1, target + 1):
                reducer.apply(state, self.events[i])
            return state
        backward_cost = current - target
        checkpoint_index, _ = self._nearest_checkpoint(target)
        forward_cost = target - checkpoint_index
        if backward_cost <= forward_cost:
            for _ in range(backward_cost):
                state = self.step_back(state)
            return state
        return self.state_at(target)

    # ------------------------------------------------------------------
    # debugger navigation, all of it a search over the recording
    # ------------------------------------------------------------------
    def next_matching(
        self,
        step: int,
        predicate: Callable[[Event], bool],
        direction: int = 1,
    ) -> int | None:
        i = step + direction
        while 0 <= i <= self.last_step:
            if predicate(self.events[i]):
                return i
            i += direction
        return None

    def step_over(self, step: int) -> int | None:
        depth = self.events[step].depth if 0 <= step <= self.last_step else 0
        return self.next_matching(
            step,
            lambda e: e.type == EventType.LINE_EXECUTED and e.depth <= depth,
        )

    def step_into(self, step: int) -> int | None:
        return self.next_matching(step, lambda e: e.type == EventType.FUNCTION_ENTERED)

    def step_out(self, step: int) -> int | None:
        if not (0 <= step <= self.last_step):
            return None
        frame = self.events[step].frame
        return self.next_matching(
            step,
            lambda e: e.type == EventType.FUNCTION_EXITED and e.frame == frame,
        )

    def run_to_line(self, step: int, lines: Iterable[int], direction: int = 1) -> int | None:
        wanted = set(lines)
        return self.next_matching(
            step,
            lambda e: e.type == EventType.LINE_EXECUTED and e.line in wanted,
            direction,
        )

    def previous_write(self, step: int, name: str) -> int | None:
        """Where did this variable last change?  The provenance query."""
        return self.next_matching(
            step + 1,
            lambda e: e.type
            in (EventType.VARIABLE_WRITTEN, EventType.VARIABLE_CREATED)
            and e.payload.get("name") == name,
            direction=-1,
        )
