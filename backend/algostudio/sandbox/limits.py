"""Per-platform process limits.

POSIX gets real ``setrlimit`` caps and a process group we can signal as a unit.
Windows gets a new process group and a tree kill; the rlimit equivalents
(job objects) are not wired up in the MVP.

The important property is that **the caller learns which limits were actually
installed** -- ``applied()`` feeds ``SandboxResult.policy_applied``, which the
UI surfaces.  A run with weaker isolation must say so rather than imply the
full policy was in force.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from typing import Any, Callable

IS_WINDOWS = sys.platform.startswith("win")

try:  # POSIX only
    import resource  # type: ignore
except ImportError:  # pragma: no cover - Windows
    resource = None  # type: ignore


def applied(policy: Any) -> dict[str, bool]:
    posix = resource is not None
    return {
        "separate_process": True,
        "clean_environment": True,
        "isolated_interpreter": True,
        "import_allowlist": True,
        "builtins_denylist": True,
        "event_budget": True,
        "wall_clock_timeout": True,
        "cpu_limit": posix,
        "memory_limit": posix,
        "file_size_limit": posix,
        "open_files_limit": posix,
        "process_group_kill": True,
        "network_disabled": False,   # only true under the container sandbox
        "readonly_filesystem": False,
    }


def preexec(policy: Any) -> Callable[[], None] | None:
    """``preexec_fn`` installing rlimits and a new session (POSIX only)."""
    if resource is None:
        return None

    cpu = int(max(1, policy.max_cpu_seconds))
    mem = int(policy.max_memory_mb) * 1024 * 1024

    def _apply() -> None:  # pragma: no cover - runs in the forked child
        try:
            os.setsid()
        except Exception:
            pass
        for res, soft, hard in (
            (resource.RLIMIT_CPU, cpu, cpu + 1),
            (resource.RLIMIT_AS, mem, mem),
            (resource.RLIMIT_FSIZE, 0, 0),
            (resource.RLIMIT_NOFILE, 64, 64),
            (resource.RLIMIT_CORE, 0, 0),
        ):
            try:
                resource.setrlimit(res, (soft, hard))
            except Exception:
                pass

    return _apply


def creation_flags() -> int:
    if IS_WINDOWS:
        return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return 0


def clean_env() -> dict[str, str]:
    """A minimal environment: server secrets are never inherited by user code."""
    env = {
        "PYTHONHASHSEED": "0",       # deterministic set/dict iteration order
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "PATH": os.environ.get("PATH", ""),
        "LANG": "C.UTF-8",
    }
    if IS_WINDOWS:
        for key in ("SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "PATHEXT"):
            if key in os.environ:
                env[key] = os.environ[key]
    return env


def kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the child and anything it spawned."""
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        pass
    finally:
        try:
            proc.kill()
        except Exception:
            pass


def peak_rss_mb(proc: subprocess.Popen) -> float | None:
    """Best-effort peak RSS of the finished child (POSIX only)."""
    if resource is None:
        return None
    try:
        usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    except Exception:  # pragma: no cover
        return None
    scale = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return round(usage.ru_maxrss / scale, 2)
