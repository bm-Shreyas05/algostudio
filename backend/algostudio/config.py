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


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


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
    #: May a visitor run source they typed themselves?  True locally, where the
    #: only person who can reach the server is the person running it.  Setting
    #: it to False turns the deployment into a curated gallery: the 49 bundled
    #: plugins still run, ``POST /executions`` and ``POST /analyze`` do not.
    #: That is the one honest way to publish a link without a container
    #: boundary -- see docs/20-deployment.md.
    allow_arbitrary_code: bool = field(
        default_factory=lambda: _env_bool("ALGOSTUDIO_ALLOW_ARBITRARY_CODE", True)
    )
    #: Browser origins allowed to call the API.  The default is a wildcard
    #: because in development the Vite dev server is a different origin; a
    #: deployment that serves the built SPA from this same process needs no
    #: cross-origin access at all and should set an explicit list (or "none").
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: _env_list("ALGOSTUDIO_CORS_ORIGINS", ("*",))
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

    def deployment_warnings(self) -> list[str]:
        """Configuration that is fine locally and not fine on a public host.

        Reported by ``GET /health`` and by ``tools/preflight.py`` rather than
        enforced, because "fine locally" is the common case and refusing to
        start would make the development default useless.  The one combination
        that genuinely must not ship is the first: it executes source typed by
        a stranger in a process that shares the host's kernel, filesystem and
        network with the API.
        """
        warnings: list[str] = []
        if self.allow_arbitrary_code and self.sandbox_mode != "docker":
            warnings.append(
                "arbitrary code is enabled with ALGOSTUDIO_SANDBOX=subprocess: "
                "the in-process restrictions are defense in depth, not a "
                "boundary (docs/06-sandbox.md). Set ALGOSTUDIO_SANDBOX=docker "
                "or ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0 before exposing this."
            )
        if "*" in self.cors_origins:
            warnings.append(
                "CORS allows every origin; set ALGOSTUDIO_CORS_ORIGINS to the "
                "site's own origin, or to 'none' when the API and the SPA are "
                "served from the same process."
            )
        if self.retention_days <= 0:
            warnings.append(
                "ALGOSTUDIO_RETENTION_DAYS <= 0: recordings are kept forever "
                "and the data directory grows without bound."
            )
        return warnings


SETTINGS = Settings()
