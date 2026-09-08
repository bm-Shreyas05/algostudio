"""Process-isolation sandbox -- the default, and the only one that works on Windows.

Layers 1-3 of docs/06-sandbox.md: in-child budget guard, interpreter hardening,
OS process isolation.  Layer 4 (container) is ``docker_sandbox.py``.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from ..languages.base import ExecutionJob
from ..languages.registry import get as get_frontend
from . import limits
from .base import SandboxPolicy, SandboxResult, Status


class SubprocessSandbox:
    mode = "subprocess"

    def run(self, job: ExecutionJob, policy: SandboxPolicy, job_dir: Path) -> SandboxResult:
        job_dir.mkdir(parents=True, exist_ok=True)
        events_path = job_dir / "events.jsonl"
        events_path.touch()

        payload = job.to_dict()
        payload["budget"] = policy.budget()
        payload["allowed_modules"] = list(
            policy.allowed_modules
            or getattr(get_frontend(job.language), "default_allowed_modules", list)()
        )
        if policy.dump_instrumented:
            payload["dump_instrumented"] = str(job_dir / "instrumented.py")
        (job_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")

        cmd = list(get_frontend(job.language).child_entrypoint()) + [str(job_dir)]
        # cwd is the (empty) job directory, so a program that does manage to
        # touch the filesystem cannot see the server's tree.
        started = time.perf_counter()
        proc = subprocess.Popen(
            cmd,
            cwd=str(job_dir),
            env=limits.clean_env(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            close_fds=True,
            preexec_fn=limits.preexec(policy),          # type: ignore[arg-type]
            creationflags=limits.creation_flags(),
        )

        timed_out = False
        try:
            _, stderr = proc.communicate(timeout=policy.max_seconds + 2.0)
        except subprocess.TimeoutExpired:
            timed_out = True
            limits.kill_tree(proc)
            try:
                _, stderr = proc.communicate(timeout=3.0)
            except Exception:  # pragma: no cover
                stderr = ""
        wall_ms = (time.perf_counter() - started) * 1000.0

        result = _read_result(job_dir)
        status: Status = result.get("status", "internal_error")
        if timed_out:
            # The child ignored (or never reached) the in-process budget guard.
            status = "timeout"

        return SandboxResult(
            status=status,
            events_path=events_path,
            job_dir=job_dir,
            exit_code=proc.returncode,
            wall_ms=wall_ms,
            event_count=int(result.get("event_count", 0)),
            counters=result.get("counters") or {},
            error=result.get("error"),
            peak_rss_mb=limits.peak_rss_mb(proc),
            policy_applied=limits.applied(policy),
            mode=self.mode,
            diagnostics=(stderr or "").strip(),
        )


def _read_result(job_dir: Path) -> dict:
    path = job_dir / "result.json"
    if not path.exists():
        # The child died before writing its summary: any events already flushed
        # are still usable, which is the whole point of streaming to a file.
        return {"status": "killed", "event_count": _count_lines(job_dir / "events.jsonl")}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # pragma: no cover
        return {"status": "internal_error"}


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as fh:
        return sum(1 for _ in fh)
