"""Metadata persistence.

Stdlib ``sqlite3`` with a thin DAL rather than an ORM: the access patterns are
a handful of fixed queries, the schema below is plain portable SQL, and keeping
the dependency list short matters more here than object mapping would buy.
Moving to Postgres is a driver swap plus the usual type adjustments.

Events are not stored here -- see ``eventlog.py`` for why.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS execution (
  id              TEXT PRIMARY KEY,
  project_id      TEXT,
  algorithm_id    TEXT,
  language        TEXT NOT NULL,
  source          TEXT NOT NULL,
  source_hash     TEXT NOT NULL,
  inputs_json     TEXT NOT NULL DEFAULT '{}',
  granularity     TEXT NOT NULL,
  status          TEXT NOT NULL,
  error_json      TEXT,
  event_count     INTEGER NOT NULL DEFAULT 0,
  storage_dir     TEXT NOT NULL,
  sandbox_mode    TEXT NOT NULL,
  policy_json     TEXT NOT NULL DEFAULT '{}',
  capability_json TEXT NOT NULL DEFAULT '{}',
  wall_ms         REAL DEFAULT 0,
  peak_rss_mb     REAL,
  created_at      REAL NOT NULL,
  finished_at     REAL
);
CREATE INDEX IF NOT EXISTS ix_execution_cache
  ON execution(source_hash, granularity, status);
CREATE INDEX IF NOT EXISTS ix_execution_created ON execution(created_at DESC);

CREATE TABLE IF NOT EXISTS execution_analytics (
  execution_id   TEXT PRIMARY KEY REFERENCES execution(id) ON DELETE CASCADE,
  analytics_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_query (
  id             TEXT PRIMARY KEY,
  execution_id   TEXT REFERENCES execution(id) ON DELETE CASCADE,
  step           INTEGER NOT NULL,
  mode           TEXT NOT NULL,
  question       TEXT NOT NULL,
  answer         TEXT,
  provider       TEXT NOT NULL,
  model          TEXT,
  grounding_json TEXT,
  tokens_in      INTEGER DEFAULT 0,
  tokens_out     INTEGER DEFAULT 0,
  latency_ms     REAL DEFAULT 0,
  created_at     REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_ai_cache
  ON ai_query(execution_id, step, mode, question);

CREATE TABLE IF NOT EXISTS session (
  id            TEXT PRIMARY KEY,
  execution_id  TEXT REFERENCES execution(id) ON DELETE CASCADE,
  share_token   TEXT UNIQUE,
  ui_state_json TEXT NOT NULL DEFAULT '{}',
  created_at    REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS benchmark (
  id              TEXT PRIMARY KEY,
  name            TEXT,
  input_spec_json TEXT NOT NULL,
  runs_json       TEXT NOT NULL DEFAULT '[]',
  created_at      REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    # ------------------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            self._local.conn = conn
        return conn

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    # -- executions ---------------------------------------------------------
    def create_execution(self, **fields: Any) -> str:
        execution_id = fields.pop("id", None) or new_id("ex")
        fields.setdefault("created_at", time.time())
        columns = ", ".join(["id", *fields])
        markers = ", ".join(["?"] * (len(fields) + 1))
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO execution ({columns}) VALUES ({markers})",
                [execution_id, *fields.values()],
            )
        return execution_id

    def update_execution(self, execution_id: str, **fields: Any) -> None:
        if not fields:
            return
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE execution SET {assignments} WHERE id = ?",
                [*fields.values(), execution_id],
            )

    def get_execution(self, execution_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution WHERE id = ?", (execution_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_executions(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, algorithm_id, language, granularity, status, "
                "event_count, wall_ms, created_at FROM execution "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def find_cached(self, source_hash: str, granularity: str) -> dict[str, Any] | None:
        """Identical code and settings -> reuse the recording.

        A classroom running the same example thirty times pays for one
        execution, and the demo is instant.
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution WHERE source_hash = ? AND granularity = ? "
                "AND status IN ('ok','error','budget_exceeded') "
                "ORDER BY created_at DESC LIMIT 1",
                (source_hash, granularity),
            ).fetchone()
        return dict(row) if row else None

    def delete_execution(self, execution_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM execution WHERE id = ?", (execution_id,))

    # -- analytics ----------------------------------------------------------
    def save_analytics(self, execution_id: str, analytics: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO execution_analytics VALUES (?, ?)",
                (execution_id, json.dumps(analytics, default=str)),
            )

    def get_analytics(self, execution_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT analytics_json FROM execution_analytics WHERE execution_id = ?",
                (execution_id,),
            ).fetchone()
        return json.loads(row["analytics_json"]) if row else None

    # -- ai -----------------------------------------------------------------
    def find_ai_answer(self, execution_id: str, step: int, mode: str,
                       question: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM ai_query WHERE execution_id = ? AND step = ? "
                "AND mode = ? AND question = ? ORDER BY created_at DESC LIMIT 1",
                (execution_id, step, mode, question),
            ).fetchone()
        return dict(row) if row else None

    def save_ai_answer(self, **fields: Any) -> str:
        query_id = fields.pop("id", None) or new_id("ai")
        fields.setdefault("created_at", time.time())
        columns = ", ".join(["id", *fields])
        markers = ", ".join(["?"] * (len(fields) + 1))
        with self.connect() as conn:
            conn.execute(
                f"INSERT INTO ai_query ({columns}) VALUES ({markers})",
                [query_id, *fields.values()],
            )
        return query_id

    # -- sessions / benchmarks ---------------------------------------------
    def save_session(self, execution_id: str, ui_state: dict[str, Any]) -> dict[str, str]:
        session_id, token = new_id("se"), uuid.uuid4().hex[:16]
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO session VALUES (?, ?, ?, ?, ?)",
                (session_id, execution_id, token,
                 json.dumps(ui_state, default=str), time.time()),
            )
        return {"session_id": session_id, "share_token": token}

    def get_session(self, token: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM session WHERE share_token = ?", (token,)
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["ui_state"] = json.loads(data.pop("ui_state_json") or "{}")
        return data

    def save_benchmark(self, name: str, spec: dict[str, Any],
                       runs: list[dict[str, Any]]) -> str:
        benchmark_id = new_id("bm")
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO benchmark VALUES (?, ?, ?, ?, ?)",
                (benchmark_id, name, json.dumps(spec, default=str),
                 json.dumps(runs, default=str), time.time()),
            )
        return benchmark_id

    def get_benchmark(self, benchmark_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM benchmark WHERE id = ?", (benchmark_id,)
            ).fetchone()
        if not row:
            return None
        data = dict(row)
        data["input_spec"] = json.loads(data.pop("input_spec_json"))
        data["runs"] = json.loads(data.pop("runs_json"))
        return data


def new_id(prefix: str) -> str:
    # Short on purpose: ids become directory names, and Windows still enforces
    # a 260-character path limit unless long paths are enabled.
    return f"{prefix}_{uuid.uuid4().hex[:12]}"
