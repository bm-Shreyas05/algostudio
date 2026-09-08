"""Sandbox interface and policy.

Everything downstream depends on ``SandboxResult``, never on how isolation was
achieved.  That is what lets ``DockerSandbox`` and ``SubprocessSandbox`` be
swapped by configuration, and what would let a future Firecracker or WASM
runner slot in unchanged.

Read docs/06-sandbox.md for the threat model.  Short version: the in-process
restrictions are defense in depth; the OS process and (in production) the
container are the actual boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from ..languages.base import ExecutionJob

Status = Literal[
    "ok", "error", "timeout", "budget_exceeded", "killed", "internal_error"
]


@dataclass(frozen=True, slots=True)
class SandboxPolicy:
    max_seconds: float = 10.0
    max_cpu_seconds: float = 5.0
    max_memory_mb: int = 256
    max_events: int = 200_000
    max_output_bytes: int = 1 << 20
    max_recursion: int = 200
    max_heap_objects: int = 50_000
    allowed_modules: tuple[str, ...] = ()
    network: bool = False
    dump_instrumented: bool = False

    def budget(self) -> dict[str, Any]:
        """The subset the in-child budget guard enforces."""
        return {
            "max_events": self.max_events,
            "max_seconds": self.max_seconds,
            "max_output_bytes": self.max_output_bytes,
            "max_recursion": self.max_recursion,
            "max_heap_objects": self.max_heap_objects,
        }

    def tightened(self, **overrides: Any) -> "SandboxPolicy":
        """Apply request overrides.  Limits may only ever be lowered."""
        current = {
            f: getattr(self, f)
            for f in (
                "max_seconds", "max_cpu_seconds", "max_memory_mb", "max_events",
                "max_output_bytes", "max_recursion", "max_heap_objects",
            )
        }
        for key, value in overrides.items():
            if value is None or key not in current:
                continue
            current[key] = min(current[key], value)
        return SandboxPolicy(
            allowed_modules=self.allowed_modules,
            network=self.network,
            dump_instrumented=self.dump_instrumented,
            **current,
        )


@dataclass(slots=True)
class SandboxResult:
    status: Status
    events_path: Path
    job_dir: Path
    exit_code: int | None = None
    wall_ms: float = 0.0
    event_count: int = 0
    counters: dict[str, int] = field(default_factory=dict)
    error: dict[str, Any] | None = None
    peak_rss_mb: float | None = None
    #: Which limits were actually installed.  Degradation is recorded, never
    #: hidden -- a run without a memory cap says so.
    policy_applied: dict[str, bool] = field(default_factory=dict)
    mode: str = "subprocess"
    diagnostics: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "exit_code": self.exit_code,
            "wall_ms": round(self.wall_ms, 3),
            "event_count": self.event_count,
            "counters": self.counters,
            "error": self.error,
            "peak_rss_mb": self.peak_rss_mb,
            "policy_applied": self.policy_applied,
            "mode": self.mode,
            "diagnostics": self.diagnostics[:2000],
        }


class Sandbox(Protocol):
    mode: str

    def run(self, job: ExecutionJob, policy: SandboxPolicy, job_dir: Path) -> SandboxResult:
        ...
