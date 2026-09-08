"""The execution pipeline, end to end.

    analyze -> instrument+sandbox -> lift -> reduce+checkpoint -> analyse -> persist

This is the composition root.  Everything it calls is a plain function or class
that can be used without HTTP, which is what lets the CLI tools, the tests and
the benchmark harness drive the same code path the API does.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..analytics import metrics
from ..config import SETTINGS, Settings
from ..core.errors import (
    AlgoStudioError, CapabilityReport, InputTooLargeError, Severity,
    UnsupportedConstructError,
)
from ..core.events import Event
from ..languages.base import ExecutionJob
from ..languages.registry import get as get_frontend
from ..lifters.pipeline import LifterPipeline
from ..plugins.registry import REGISTRY as PLUGINS
from ..sandbox.base import SandboxPolicy, SandboxResult
from ..shapes.resolver import ViewResolver
from ..state.model import ExecutionState
from ..state.timeline import Timeline, normalize_ids
from ..store import eventlog
from ..store.db import Database

_TIMELINE_CACHE: dict[str, Timeline] = {}
_TIMELINE_ORDER: list[str] = []
_TIMELINE_CACHE_SIZE = 8


@dataclass(slots=True)
class RunRequest:
    source: str
    language: str = "python"
    granularity: str = "standard"
    inputs: dict[str, Any] = field(default_factory=dict)
    entry: str | None = None
    stdin: str = ""
    algorithm_id: str | None = None
    strict_capabilities: bool = False
    lifters: bool | None = None
    max_seconds: float | None = None
    max_events: int | None = None
    use_cache: bool | None = None


@dataclass(slots=True)
class RunResult:
    execution_id: str
    status: str
    cached: bool
    capability_report: dict[str, Any]
    event_count: int
    error: dict[str, Any] | None = None
    wall_ms: float = 0.0


class ExecutionService:
    def __init__(self, settings: Settings | None = None, db: Database | None = None) -> None:
        self.settings = settings or SETTINGS
        self.settings.ensure_dirs()
        self.db = db or Database(self.settings.db_path)
        self.resolver = ViewResolver()

    # ==================================================================
    # analysis (never executes anything)
    # ==================================================================
    def analyze(self, source: str, language: str = "python") -> dict[str, Any]:
        self._check_size(source)
        analysis = get_frontend(language).analyze(source)
        return analysis.to_dict()

    # ==================================================================
    # run
    # ==================================================================
    def run(self, request: RunRequest,
            on_progress: Callable[[list[Event]], None] | None = None) -> RunResult:
        self._check_size(request.source)
        frontend = get_frontend(request.language)
        analysis = frontend.analyze(request.source)
        capability = analysis.capability

        if request.strict_capabilities and not capability.supported:
            issue = capability.blocking[0]
            raise UnsupportedConstructError(
                issue.message, line=issue.line, col=issue.col, code=issue.code
            )

        source_hash = self._hash(request)
        use_cache = (
            self.settings.cache_executions if request.use_cache is None
            else request.use_cache
        )
        if use_cache:
            cached = self.db.find_cached(source_hash, request.granularity)
            if cached and Path(cached["storage_dir"]).exists():
                return RunResult(
                    execution_id=cached["id"],
                    status=cached["status"],
                    cached=True,
                    capability_report=json.loads(cached["capability_json"] or "{}"),
                    event_count=cached["event_count"],
                    error=json.loads(cached["error_json"] or "null"),
                    wall_ms=cached["wall_ms"] or 0.0,
                )

        execution_id = self.db.create_execution(
            algorithm_id=request.algorithm_id,
            language=request.language,
            source=request.source,
            source_hash=source_hash,
            inputs_json=json.dumps(request.inputs, default=str),
            granularity=request.granularity,
            status="running",
            storage_dir="",
            sandbox_mode=self.settings.sandbox_mode,
            capability_json=json.dumps(capability.to_dict()),
        )
        directory = self.settings.executions_dir / execution_id
        directory.mkdir(parents=True, exist_ok=True)
        self.db.update_execution(execution_id, storage_dir=str(directory))

        policy = self._policy(request)
        job = ExecutionJob(
            language=request.language,
            source=request.source,
            granularity=request.granularity,
            entry=request.entry,
            inputs=request.inputs,
            stdin=request.stdin,
            budget=policy.budget(),
            allowed_modules=list(policy.allowed_modules) or None,
        )

        started = time.perf_counter()
        sandbox = self._sandbox()
        result: SandboxResult = sandbox.run(job, policy, directory / "s")
        wall_ms = (time.perf_counter() - started) * 1000.0

        raw = eventlog.read_raw(result.events_path)
        use_lifters = (
            self.settings.lifters_enabled if request.lifters is None else request.lifters
        )
        events = LifterPipeline().process(raw) if use_lifters else list(raw)
        normalize_ids(events)
        if on_progress:
            on_progress(events)

        eventlog.EventLogWriter(directory).write_all(events)
        analytics = metrics.compute(events)
        analytics.duration_ms = analytics.duration_ms or wall_ms

        eventlog.write_json(
            directory / "meta.json",
            {
                "execution_id": execution_id,
                "language": request.language,
                "granularity": request.granularity,
                "algorithm_id": request.algorithm_id,
                "entry": request.entry,
                "inputs": request.inputs,
                "source": request.source,
                "source_map": analysis.source_map.to_dict(),
                "structure": analysis.structure,
                "capability_report": capability.to_dict(),
                "policy_applied": result.policy_applied,
                "sandbox": result.to_dict(),
                "lifters": use_lifters,
            },
        )
        self.db.save_analytics(execution_id, analytics.to_dict())
        self.db.update_execution(
            execution_id,
            status=result.status,
            error_json=json.dumps(result.error) if result.error else None,
            event_count=len(events),
            wall_ms=wall_ms,
            peak_rss_mb=result.peak_rss_mb,
            policy_json=json.dumps(result.policy_applied),
            finished_at=time.time(),
        )
        _invalidate(execution_id)

        return RunResult(
            execution_id=execution_id,
            status=result.status,
            cached=False,
            capability_report=capability.to_dict(),
            event_count=len(events),
            error=result.error,
            wall_ms=wall_ms,
        )

    def run_algorithm(self, algorithm_id: str, inputs: dict[str, Any] | None = None,
                      granularity: str = "standard", **kwargs: Any) -> RunResult:
        """Run a packaged plugin -- through exactly the same pipeline as user code."""
        plugin = PLUGINS.get(algorithm_id)
        return self.run(
            RunRequest(
                source=plugin.source,
                granularity=granularity,
                inputs=plugin.bind_inputs(inputs),
                entry=plugin.entry,
                algorithm_id=plugin.id,
                **kwargs,
            )
        )

    # ==================================================================
    # navigation
    # ==================================================================
    def timeline(self, execution_id: str) -> Timeline:
        cached = _TIMELINE_CACHE.get(execution_id)
        if cached is not None:
            return cached
        record = self._require(execution_id)
        events = eventlog.EventLog(Path(record["storage_dir"])).read_all()
        timeline = Timeline(events, self.settings.checkpoint_interval)
        _remember(execution_id, timeline)
        return timeline

    def state_at(self, execution_id: str, step: int) -> ExecutionState:
        return self.timeline(execution_id).state_at(step)

    def events(self, execution_id: str, offset: int = 0, limit: int = 2000,
               types: set[str] | None = None, frame: int | None = None,
               line: int | None = None) -> dict[str, Any]:
        record = self._require(execution_id)
        log = eventlog.EventLog(Path(record["storage_dir"]))
        total = len(log)
        if types or frame is not None or line is not None:
            selected = [
                e for e in log.iter_all()
                if (not types or _type_name(e) in types)
                and (frame is None or e.frame == frame)
                and (line is None or e.line == line)
            ]
            window = selected[offset: offset + limit]
            matched = len(selected)
        else:
            window = log.slice(offset, limit)
            matched = total
        return {
            "offset": offset,
            "limit": limit,
            "total": total,
            "matched": matched,
            "next_offset": offset + len(window) if offset + len(window) < matched else None,
            "events": [e.to_dict() for e in window],
        }

    def views(self, execution_id: str, step: int) -> list[dict[str, Any]]:
        record = self._require(execution_id)
        state = self.state_at(execution_id, step)
        hints: list[dict[str, Any]] = []
        if record.get("algorithm_id"):
            try:
                plugin = PLUGINS.get(record["algorithm_id"])
                hints = [h.to_dict() for h in plugin.viz_hints]
            except AlgoStudioError:
                hints = []
        # Views are resolved against the FINAL heap and applied to every step,
        # so an empty `visited = set()` renders as a set from step 0 rather than
        # popping into existence when it happens to fill.
        final = self.state_at(execution_id, self.timeline(execution_id).last_step)
        final.step = state.step
        final.counters = state.counters
        plans = self.resolver.resolve(final, hints)
        return [p.to_dict() for p in plans]

    def analytics(self, execution_id: str) -> dict[str, Any]:
        stored = self.db.get_analytics(execution_id)
        if stored is not None:
            return stored
        return metrics.compute(self.timeline(execution_id).events).to_dict()

    def meta(self, execution_id: str) -> dict[str, Any]:
        record = self._require(execution_id)
        return eventlog.read_json(Path(record["storage_dir"]) / "meta.json", {}) or {}

    def summary(self, execution_id: str) -> dict[str, Any]:
        record = self._require(execution_id)
        meta = self.meta(execution_id)
        return {
            "execution_id": record["id"],
            "status": record["status"],
            "language": record["language"],
            "algorithm_id": record["algorithm_id"],
            "granularity": record["granularity"],
            "event_count": record["event_count"],
            "wall_ms": record["wall_ms"],
            "peak_rss_mb": record["peak_rss_mb"],
            "sandbox_mode": record["sandbox_mode"],
            "policy_applied": json.loads(record["policy_json"] or "{}"),
            "capability_report": json.loads(record["capability_json"] or "{}"),
            "error": json.loads(record["error_json"] or "null"),
            "source": record["source"],
            "inputs": json.loads(record["inputs_json"] or "{}"),
            "source_map": meta.get("source_map", {}),
            "structure": meta.get("structure", {}),
            "lifters": meta.get("lifters", True),
            "created_at": record["created_at"],
            "finished_at": record["finished_at"],
        }

    def delete(self, execution_id: str) -> None:
        record = self.db.get_execution(execution_id)
        if record and record["storage_dir"]:
            _rmtree(Path(record["storage_dir"]))
        self.db.delete_execution(execution_id)
        _invalidate(execution_id)

    # ==================================================================
    # internals
    # ==================================================================
    def _require(self, execution_id: str) -> dict[str, Any]:
        from ..core.errors import ExecutionNotFoundError

        record = self.db.get_execution(execution_id)
        if record is None:
            raise ExecutionNotFoundError(f"no execution {execution_id!r}")
        return record

    def _check_size(self, source: str) -> None:
        if len(source.encode("utf-8")) > self.settings.max_source_bytes:
            raise InputTooLargeError(
                f"source exceeds {self.settings.max_source_bytes} bytes"
            )

    def _hash(self, request: RunRequest) -> str:
        payload = json.dumps(
            {
                "source": request.source,
                "inputs": request.inputs,
                "entry": request.entry,
                "stdin": request.stdin,
                "language": request.language,
                "lifters": request.lifters,
            },
            sort_keys=True, default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _policy(self, request: RunRequest) -> SandboxPolicy:
        frontend = get_frontend(request.language)
        allowed = tuple(getattr(frontend, "default_allowed_modules", list)())
        base = SandboxPolicy(
            max_seconds=self.settings.max_seconds,
            max_events=self.settings.max_events,
            max_memory_mb=self.settings.max_memory_mb,
            allowed_modules=allowed,
        )
        return base.tightened(
            max_seconds=request.max_seconds, max_events=request.max_events
        )

    def _sandbox(self):
        if self.settings.sandbox_mode == "docker":
            from ..sandbox.docker_sandbox import DockerSandbox

            return DockerSandbox()
        from ..sandbox.subprocess_sandbox import SubprocessSandbox

        return SubprocessSandbox()


def _type_name(ev: Event) -> str:
    return ev.type.value if hasattr(ev.type, "value") else str(ev.type)


def _remember(execution_id: str, timeline: Timeline) -> None:
    _TIMELINE_CACHE[execution_id] = timeline
    _TIMELINE_ORDER.append(execution_id)
    while len(_TIMELINE_ORDER) > _TIMELINE_CACHE_SIZE:
        oldest = _TIMELINE_ORDER.pop(0)
        _TIMELINE_CACHE.pop(oldest, None)


def _invalidate(execution_id: str) -> None:
    _TIMELINE_CACHE.pop(execution_id, None)
    if execution_id in _TIMELINE_ORDER:
        _TIMELINE_ORDER.remove(execution_id)


def _rmtree(path: Path) -> None:
    import shutil

    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
