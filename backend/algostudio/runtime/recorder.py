"""The event recorder -- runs inside the sandbox child.

Responsibilities: allocate event ids and logical steps, track the frame stack,
encode values, enforce the execution budget, and serialize events as JSONL.

This module is deliberately import-light (stdlib + ``algostudio.core``).  It
executes in the same process as untrusted code, so every import here enlarges
the reachable surface.
"""

from __future__ import annotations

import json
import time
from typing import Any, TextIO

from ..core.errors import ExecutionBudgetExceeded
from ..core.events import Event, EventType, Loc
from ..core.values import EncodingLimits, ValueEncoder

NEWLINE = chr(10)


class Budget:
    """Hard limits enforced from inside the instrumented program.

    Living here rather than only at the OS level is what turns an infinite loop
    into a *diagnosable partial trace* instead of a hang: the guard raises an
    ordinary exception at a known point, the stack unwinds, and the event file
    is flushed.
    """

    __slots__ = (
        "max_events", "max_seconds", "max_output_bytes",
        "max_heap_objects", "max_recursion", "started",
    )

    def __init__(
        self,
        max_events: int = 200_000,
        max_seconds: float = 10.0,
        max_output_bytes: int = 1 << 20,
        max_heap_objects: int = 50_000,
        max_recursion: int = 200,
    ) -> None:
        self.max_events = max_events
        self.max_seconds = max_seconds
        self.max_output_bytes = max_output_bytes
        self.max_heap_objects = max_heap_objects
        self.max_recursion = max_recursion
        self.started = 0.0


class Frame:
    __slots__ = ("frame_id", "func_id", "name", "call_line", "line")

    def __init__(self, frame_id: int, func_id: str, name: str, call_line: int) -> None:
        self.frame_id = frame_id
        self.func_id = func_id
        self.name = name
        self.call_line = call_line
        self.line = call_line


class Recorder:
    """Single instance per execution, owned by the sandbox child."""

    def __init__(
        self,
        sink: TextIO,
        budget: Budget | None = None,
        granularity: str = "standard",
        flush_every: int = 512,
    ) -> None:
        self.sink = sink
        self.budget = budget or Budget()
        self.granularity = granularity
        self.encoder = ValueEncoder(
            EncodingLimits(max_heap_objects=self.budget.max_heap_objects)
        )
        self.n = 0                      # next event id / logical step
        self.output_bytes = 0
        self.frames: list[Frame] = [Frame(0, "<module>", "<module>", 0)]
        self._next_frame_id = 1
        self._buf: list[str] = []
        self._flush_every = flush_every
        self._t0 = time.perf_counter()
        self.budget.started = self._t0
        self.finished = False
        self.loop_counters: dict[str, int] = {}
        self.counters: dict[str, int] = {}
        self._out_buf: dict[str, str] = {"stdout": "", "stderr": ""}

    # -- budget -------------------------------------------------------------
    def tick(self) -> None:
        self.n += 1
        b = self.budget
        if self.n > b.max_events:
            self._budget_stop("event limit reached", b.max_events)
        if (self.n & 0x3FF) == 0 and (time.perf_counter() - self._t0) > b.max_seconds:
            self._budget_stop("time limit reached", b.max_seconds)

    def _budget_stop(self, reason: str, limit: Any) -> None:
        if not self.finished:
            self.finished = True
            self._write(
                Event(
                    id=self.n,
                    step=self.n,
                    type=EventType.BUDGET_EXCEEDED,
                    t=self.elapsed,
                    frame=self.frame_id,
                    depth=self.depth,
                    payload={"reason": reason, "limit": limit},
                )
            )
            self.flush()
        raise ExecutionBudgetExceeded(reason, limit)

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self._t0

    @property
    def current_line(self) -> int:
        return self.frames[-1].line

    # -- frames -------------------------------------------------------------
    @property
    def frame_id(self) -> int:
        return self.frames[-1].frame_id

    @property
    def depth(self) -> int:
        return len(self.frames) - 1

    def push_frame(self, func_id: str, name: str, call_line: int) -> int:
        if self.depth >= self.budget.max_recursion:
            raise RecursionError(
                f"maximum recursion depth ({self.budget.max_recursion}) exceeded "
                f"in AlgoStudio while calling {name!r}"
            )
        fid = self._next_frame_id
        self._next_frame_id += 1
        self.frames.append(Frame(fid, func_id, name, call_line))
        return fid

    def pop_frame(self, func_id: str) -> Frame | None:
        # Tolerant pop: unwinding through non-instrumented code can leave the
        # stack deeper than expected, so unwind to the matching frame.
        for i in range(len(self.frames) - 1, 0, -1):
            if self.frames[i].func_id == func_id:
                frame = self.frames[i]
                del self.frames[i:]
                return frame
        return None

    # -- emission -----------------------------------------------------------
    def emit(
        self,
        etype: EventType,
        payload: dict[str, Any] | None = None,
        line: int = 0,
        meta: dict[str, Any] | None = None,
        frame: int | None = None,
    ) -> Event:
        if line:
            self.frames[-1].line = line
        if etype not in (EventType.STDOUT_WRITE, EventType.STDERR_WRITE):
            self._flush_output()
        self._drain_new_objects(line)
        self.tick()
        ev = Event(
            id=self.n,
            step=self.n,
            type=etype,
            t=self.elapsed,
            frame=self.frame_id if frame is None else frame,
            depth=self.depth,
            loc=Loc(line) if line else None,
            payload=payload or {},
            meta=meta or {},
        )
        self._write(ev)
        return ev

    def _drain_new_objects(self, line: int) -> None:
        """Emit OBJECT_CREATED for heap objects first seen since the last event.

        Called before the event that referenced them so the reducer always has
        the record available when it applies the referencing event.
        """
        new = self.encoder.take_new()
        for ref, rec in new:
            self.n += 1
            self._write(
                Event(
                    id=self.n,
                    step=self.n,
                    type=EventType.OBJECT_CREATED,
                    t=self.elapsed,
                    frame=self.frame_id,
                    depth=self.depth,
                    loc=Loc(line) if line else None,
                    payload={
                        "ref": ref,
                        "kind": rec.get("t"),
                        "snapshot": rec,
                    },
                )
            )

    def _write(self, ev: Event) -> None:
        self._buf.append(ev.to_json())
        if len(self._buf) >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        if self._buf:
            self.sink.write("\n".join(self._buf))
            self.sink.write("\n")
            self.sink.flush()
            self._buf.clear()

    # -- value helpers ------------------------------------------------------
    def enc(self, value: Any) -> dict[str, Any]:
        return self.encoder.encode(value)

    def enc_refresh(self, value: Any) -> dict[str, Any]:
        return self.encoder.encode(value, refresh=True)

    def ref_name(self, obj: Any, name: str) -> None:
        if self.encoder.known(obj):
            self.encoder.name_ref(self.encoder.ref_for(obj), name)

    def name_for(self, obj: Any) -> str | None:
        if self.encoder.known(obj):
            return self.encoder.name_of(self.encoder.ref_for(obj))
        return None

    # -- output capture -----------------------------------------------------
    def write_output(self, text: str, stream: str = "stdout") -> None:
        """Buffer program output, emitting one event per completed line.

        ``print("a", b)`` calls ``write`` four times (arg, sep, arg, end).
        Emitting an event per call would quadruple the console's event count for
        no information gain, so writes are coalesced up to the newline.
        """
        if not text:
            return
        remaining = self.budget.max_output_bytes - self.output_bytes
        if remaining <= 0:
            return
        raw = text.encode("utf-8", "replace")
        truncated = False
        if len(raw) > remaining:
            text = raw[:remaining].decode("utf-8", "ignore")
            truncated = True
        self.output_bytes += len(text.encode("utf-8", "replace"))
        self._out_buf[stream] += text
        if NEWLINE in text or truncated:
            self._flush_output(stream, truncated)

    def _flush_output(self, only: str | None = None, truncated: bool = False) -> None:
        for stream in (only,) if only else ("stdout", "stderr"):
            buf = self._out_buf.get(stream) or ""
            if not buf:
                continue
            if not truncated and not buf.endswith(NEWLINE):
                head, sep, tail = buf.rpartition(NEWLINE)
                if not sep:
                    continue
                buf, self._out_buf[stream] = head + sep, tail
            else:
                self._out_buf[stream] = ""
            etype = (
                EventType.STDOUT_WRITE if stream == "stdout" else EventType.STDERR_WRITE
            )
            payload: dict[str, Any] = {"text": buf, "len": len(buf)}
            if truncated:
                payload["trunc"] = True
            self.n += 1
            self._write(
                Event(
                    id=self.n,
                    step=self.n,
                    type=etype,
                    t=self.elapsed,
                    frame=self.frame_id,
                    depth=self.depth,
                    loc=Loc(self.current_line) if self.current_line else None,
                    payload=payload,
                )
            )

    def bump(self, name: str, delta: int = 1) -> int:
        self.counters[name] = self.counters.get(name, 0) + delta
        return self.counters[name]

    # -- lifecycle ----------------------------------------------------------
    def program_started(self, meta: dict[str, Any]) -> None:
        self.emit(EventType.PROGRAM_STARTED, meta)

    def program_finished(self, status: str, extra: dict[str, Any] | None = None) -> None:
        if self.finished:
            self.flush()
            return
        self.finished = True
        for stream in ("stdout", "stderr"):
            if self._out_buf.get(stream):
                self._flush_output(stream, truncated=True)
        payload = {
            "status": status,
            "duration_ms": round(self.elapsed * 1000, 3),
            "counters": dict(self.counters),
        }
        if extra:
            payload.update(extra)
        # Emit directly: program_finished must succeed even at the budget cap.
        self.n += 1
        self._write(
            Event(
                id=self.n,
                step=self.n,
                type=EventType.PROGRAM_FINISHED,
                t=self.elapsed,
                frame=0,
                depth=0,
                payload=payload,
            )
        )
        self.flush()


class OutputProxy:
    """Replaces ``sys.stdout``/``sys.stderr`` so program output joins the stream.

    Consequence: printed output is ordered *within* the event stream, so the
    console panel can be scrubbed backwards in time along with everything else.
    """

    def __init__(self, recorder: Recorder, stream: str) -> None:
        self._rec = recorder
        self._stream = stream
        self.encoding = "utf-8"

    def write(self, text: str) -> int:
        if not isinstance(text, str):
            text = str(text)
        self._rec.write_output(text, self._stream)
        return len(text)

    def writelines(self, lines: Any) -> None:
        for line in lines:
            self.write(line)

    def flush(self) -> None:
        return None

    def isatty(self) -> bool:
        return False

    def fileno(self) -> int:
        raise OSError("fileno is not available in AlgoStudio")


class StdinProxy:
    """Feeds the request's ``stdin`` to ``input()`` and records each read."""

    def __init__(self, recorder: Recorder, data: str) -> None:
        self._rec = recorder
        self._lines = data.splitlines()
        self._pos = 0

    def readline(self) -> str:
        if self._pos >= len(self._lines):
            self._rec.emit(EventType.STDIN_READ, {"text": "", "eof": True})
            return ""
        line = self._lines[self._pos]
        self._pos += 1
        self._rec.emit(EventType.STDIN_READ, {"text": line})
        return line + "\n"

    def read(self, n: int = -1) -> str:
        rest = "\n".join(self._lines[self._pos:])
        self._pos = len(self._lines)
        self._rec.emit(EventType.STDIN_READ, {"text": rest})
        return rest


def dumps(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), default=str)
