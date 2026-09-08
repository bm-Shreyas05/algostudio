"""Settings, all environment-driven with safe defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_ROOT.parent


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class Settings:
    #: Where executions are stored.  Override with ALGOSTUDIO_DATA when the
    #: repository lives at a deep path -- execution directories become part of
    #: the path, and Windows caps it at 260 characters by default.
    data_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("ALGOSTUDIO_DATA", REPO_ROOT / "var")
        ).resolve()
    )
    #: "subprocess" (default, works everywhere) or "docker" (required for any
    #: multi-user deployment -- see docs/06-sandbox.md).
    sandbox_mode: str = field(
        default_factory=lambda: os.environ.get("ALGOSTUDIO_SANDBOX", "subprocess")
    )
    max_source_bytes: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_MAX_SOURCE", 256 * 1024))
    max_inputs_bytes: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_MAX_INPUTS", 4 * 1024 * 1024))
    max_seconds: float = field(default_factory=lambda: _env_float("ALGOSTUDIO_MAX_SECONDS", 10.0))
    max_events: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_MAX_EVENTS", 200_000))
    max_memory_mb: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_MAX_MEMORY_MB", 256))
    checkpoint_interval: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_CHECKPOINT", 64))
    lifters_enabled: bool = field(default_factory=lambda: _env_bool("ALGOSTUDIO_LIFTERS", True))
    cache_executions: bool = field(default_factory=lambda: _env_bool("ALGOSTUDIO_CACHE", True))
    retention_days: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_RETENTION_DAYS", 14))

    # -- AI -----------------------------------------------------------------
    ai_enabled: bool = field(default_factory=lambda: _env_bool("ALGOSTUDIO_AI", True))
    ai_provider: str = field(default_factory=lambda: os.environ.get("ALGOSTUDIO_AI_PROVIDER", "auto"))
    ai_model: str = field(default_factory=lambda: os.environ.get("ALGOSTUDIO_AI_MODEL", "claude-sonnet-5"))
    ai_max_context_tokens: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_AI_CONTEXT", 6000))
    ai_max_output_tokens: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_AI_OUTPUT", 800))

    # -- limits -------------------------------------------------------------
    rate_limit_runs_per_minute: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_RATE_RUNS", 30))
    rate_limit_ai_per_minute: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_RATE_AI", 20))
    max_concurrent_executions: int = field(default_factory=lambda: _env_int("ALGOSTUDIO_CONCURRENCY", 4))

    @property
    def executions_dir(self) -> Path:
        return self.data_dir / "executions"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "algostudio.db"

    def ensure_dirs(self) -> None:
        self.executions_dir.mkdir(parents=True, exist_ok=True)


SETTINGS = Settings()
