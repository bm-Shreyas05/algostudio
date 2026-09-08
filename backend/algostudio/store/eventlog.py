"""Event log storage: JSONL plus a byte-offset index.

Events are deliberately *not* in the database (docs/01 §F.4).  The log is
append-only, read sequentially or by index range, never queried relationally,
and can reach tens of megabytes -- putting it in rows would cost an order of
magnitude in serialization for no benefit.

The sidecar index makes ``events[i]`` an O(1) seek, which is what lets the API
serve a page of events, or a single event by id, without reading the file.

A useful consequence of this layout: an execution *is* a directory.  Sharing a
session is copying it.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Iterable, Iterator, Sequence

from ..core.events import Event

INDEX_ENTRY = struct.Struct("<Q")


class EventLogWriter:
    """Writes ``events.jsonl`` and ``events.idx`` together."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = directory / "events.jsonl"
        self.index_path = directory / "events.idx"

    def write_all(self, events: Sequence[Event]) -> int:
        offset = 0
        with self.jsonl_path.open("wb") as data, self.index_path.open("wb") as index:
            for ev in events:
                line = (ev.to_json() + "\n").encode("utf-8")
                index.write(INDEX_ENTRY.pack(offset))
                data.write(line)
                offset += len(line)
        return len(events)


class EventLog:
    """Random and sequential access to a stored event stream."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.jsonl_path = self.directory / "events.jsonl"
        self.index_path = self.directory / "events.idx"
        self._offsets: list[int] | None = None

    # -- index --------------------------------------------------------------
    @property
    def offsets(self) -> list[int]:
        if self._offsets is None:
            if self.index_path.exists():
                raw = self.index_path.read_bytes()
                self._offsets = [
                    INDEX_ENTRY.unpack_from(raw, i)[0]
                    for i in range(0, len(raw), INDEX_ENTRY.size)
                ]
            else:
                self._offsets = self._rebuild_index()
        return self._offsets

    def _rebuild_index(self) -> list[int]:
        offsets: list[int] = []
        if not self.jsonl_path.exists():
            return offsets
        offset = 0
        with self.jsonl_path.open("rb") as fh:
            for line in fh:
                offsets.append(offset)
                offset += len(line)
        with self.index_path.open("wb") as index:
            for value in offsets:
                index.write(INDEX_ENTRY.pack(value))
        return offsets

    def __len__(self) -> int:
        return len(self.offsets)

    # -- access -------------------------------------------------------------
    def at(self, index: int) -> Event | None:
        offsets = self.offsets
        if index < 0 or index >= len(offsets):
            return None
        with self.jsonl_path.open("rb") as fh:
            fh.seek(offsets[index])
            line = fh.readline()
        return Event.from_json(line.decode("utf-8")) if line.strip() else None

    def slice(self, offset: int = 0, limit: int = 2000) -> list[Event]:
        offsets = self.offsets
        offset = max(0, offset)
        end = min(len(offsets), offset + max(0, limit))
        if offset >= end:
            return []
        out: list[Event] = []
        with self.jsonl_path.open("rb") as fh:
            fh.seek(offsets[offset])
            for _ in range(end - offset):
                line = fh.readline()
                if not line:
                    break
                if line.strip():
                    out.append(Event.from_json(line.decode("utf-8")))
        return out

    def iter_all(self) -> Iterator[Event]:
        if not self.jsonl_path.exists():
            return
        with self.jsonl_path.open("rb") as fh:
            for line in fh:
                if line.strip():
                    yield Event.from_json(line.decode("utf-8"))

    def read_all(self) -> list[Event]:
        return list(self.iter_all())


def read_raw(path: Path) -> list[Event]:
    """Read a raw ``events.jsonl`` written by the sandbox child."""
    if not path.exists():
        return []
    out: list[Event] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(Event.from_json(line))
            except json.JSONDecodeError:
                # A partial final line means the child was killed mid-write.
                # Everything before it is still valid, and keeping it is the
                # difference between a diagnosable trace and nothing at all.
                break
    return out


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, default=str), encoding="utf-8")


def read_json(path: Path, default: object = None) -> object:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def iter_json_lines(paths: Iterable[Path]) -> Iterator[dict]:  # pragma: no cover
    for path in paths:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)
