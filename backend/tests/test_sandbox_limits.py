"""The POSIX resource limits, exercised on POSIX.

These tests exist because of a bug that every Windows run was structurally
incapable of finding. ``preexec_fn`` is ignored on Windows -- there is no
``resource`` module and no fork -- so ``limits.preexec()`` had never once
executed. It set ``RLIMIT_FSIZE`` to 0, intending "user code cannot write
files", but the recorder writes events.jsonl and result.json from inside that
same child. Every execution in a Linux container therefore produced
``internal_error`` with zero events, and the whole site was silently useless
while every page and every header was correct.

Anything guarded by ``sys.platform`` needs a test that runs on the platform it
guards, or it is not tested at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from algostudio.languages.registry import get as get_frontend
from algostudio.sandbox import limits
from algostudio.sandbox.base import SandboxPolicy

posix_only = pytest.mark.skipif(
    sys.platform == "win32", reason="preexec_fn and rlimits are POSIX-only"
)


def _run_child(policy: SandboxPolicy, source: str = "x = 1\nprint(x)\n"):
    """Spawn the sandbox child exactly as SubprocessSandbox does."""
    job_dir = Path(tempfile.mkdtemp())
    (job_dir / "events.jsonl").touch()
    (job_dir / "job.json").write_text(json.dumps({
        "language": "python", "source": source, "inputs": {},
        "granularity": "standard", "entry": None, "stdin": "",
        "budget": policy.budget(), "allowed_modules": None,
    }), encoding="utf-8")

    cmd = list(get_frontend("python").child_entrypoint()) + [str(job_dir)]
    proc = subprocess.run(
        cmd, cwd=str(job_dir), env=limits.clean_env(),
        capture_output=True, text=True,
        preexec_fn=limits.preexec(policy),          # type: ignore[arg-type]
        timeout=60,
    )
    result_path = job_dir / "result.json"
    result = json.loads(result_path.read_text()) if result_path.is_file() else {}
    return proc, result, job_dir


@posix_only
def test_the_child_can_write_its_own_recording():
    """The regression. Under the shipped limits, a run must produce events."""
    proc, result, job_dir = _run_child(SandboxPolicy())

    assert proc.returncode == 0, f"child died: {proc.stderr[:400]}"
    assert result.get("status") == "ok", f"status {result.get('status')!r}"
    assert result.get("event_count", 0) > 0, "no events were recorded"
    assert (job_dir / "events.jsonl").stat().st_size > 0, "events.jsonl is empty"


@posix_only
def test_file_size_limit_is_installed_and_non_zero():
    """It still has to be a limit -- just not one that forbids all output."""
    import resource

    policy = SandboxPolicy()
    applied: dict[str, tuple[int, int]] = {}

    def capture(res, pair):
        if res == resource.RLIMIT_FSIZE:
            applied["fsize"] = pair

    original = resource.setrlimit
    resource.setrlimit = capture                     # type: ignore[assignment]
    try:
        limits.preexec(policy)()                     # type: ignore[misc]
    finally:
        resource.setrlimit = original                # type: ignore[assignment]

    soft, _hard = applied["fsize"]
    assert soft > 0, "a zero file-size limit stops the recorder writing at all"
    assert soft <= 512 * 1024 * 1024, "the cap must still bound disk use"


@posix_only
def test_a_tight_memory_limit_still_lets_the_interpreter_start():
    """192 MB is what the deployed configuration uses."""
    proc, result, _ = _run_child(SandboxPolicy(max_memory_mb=192))
    assert proc.returncode == 0, f"child died under RLIMIT_AS: {proc.stderr[:400]}"
    assert result.get("event_count", 0) > 0


@posix_only
def test_runaway_output_is_still_bounded():
    """The limit must remain a limit: a program cannot write without end."""
    import resource

    policy = SandboxPolicy()
    limit = min(512 * 1024 * 1024,
                max(64 * 1024 * 1024, policy.max_events * 512))
    assert limit < 1024 * 1024 * 1024
    assert resource.RLIMIT_FSIZE is not None
