"""Container sandbox -- the boundary that actually holds.

Enabled with ``ALGOSTUDIO_SANDBOX=docker``.  This is the mode any multi-user
deployment must use: the in-process restrictions in ``runtime/policy.py`` are
defense in depth, but a determined program can get past them (see
docs/06-sandbox.md, threat T3/T4).  ``--network none``, a read-only rootfs,
dropped capabilities and hard cgroup limits are what make the guarantee real.

Cost, stated honestly: container start-up adds 150-400 ms to every run.  A warm
pool is the V2 mitigation; the MVP accepts the latency in Docker mode and
defaults to the subprocess sandbox for local development.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from ..core.errors import SandboxUnavailableError
from ..languages.base import ExecutionJob
from .base import SandboxPolicy, SandboxResult, Status
from .subprocess_sandbox import _read_result

IMAGE = "algostudio-runtime:latest"


class DockerSandbox:
    mode = "docker"

    def __init__(self, image: str = IMAGE) -> None:
        self.image = image

    def available(self) -> bool:
        return shutil.which("docker") is not None

    def run(self, job: ExecutionJob, policy: SandboxPolicy, job_dir: Path) -> SandboxResult:
        if not self.available():
            raise SandboxUnavailableError("docker is not available on this host")

        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "events.jsonl").touch()
        payload = job.to_dict()
        payload["budget"] = policy.budget()
        payload["allowed_modules"] = list(policy.allowed_modules) or None
        (job_dir / "job.json").write_text(json.dumps(payload), encoding="utf-8")

        cmd = [
            "docker", "run", "--rm",
            "--network", "none" if not policy.network else "bridge",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=16m,noexec,nosuid,nodev",
            "--memory", f"{policy.max_memory_mb}m",
            "--memory-swap", f"{policy.max_memory_mb}m",
            "--cpus", "0.5",
            "--pids-limit", "64",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--user", "65534:65534",
            # /job is writable so the child can stream events out; everything
            # else in the container is read-only.
            "-v", f"{job_dir.resolve()}:/job:rw",
            self.image, "/job",
        ]

        started = time.perf_counter()
        timed_out = False
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=policy.max_seconds + 15.0,   # + container start-up
            )
            stderr, code = proc.stderr, proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stderr, code = str(exc), None
        wall_ms = (time.perf_counter() - started) * 1000.0

        result = _read_result(job_dir)
        status: Status = "timeout" if timed_out else result.get("status", "internal_error")
        return SandboxResult(
            status=status,
            events_path=job_dir / "events.jsonl",
            job_dir=job_dir,
            exit_code=code,
            wall_ms=wall_ms,
            event_count=int(result.get("event_count", 0)),
            counters=result.get("counters") or {},
            error=result.get("error"),
            policy_applied={
                "separate_process": True,
                "clean_environment": True,
                "isolated_interpreter": True,
                "import_allowlist": True,
                "builtins_denylist": True,
                "event_budget": True,
                "wall_clock_timeout": True,
                "cpu_limit": True,
                "memory_limit": True,
                "file_size_limit": True,
                "open_files_limit": True,
                "process_group_kill": True,
                "network_disabled": not policy.network,
                "readonly_filesystem": True,
            },
            mode=self.mode,
            diagnostics=(stderr or "").strip(),
        )
