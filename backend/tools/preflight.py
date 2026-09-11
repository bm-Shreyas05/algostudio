"""Check whether this configuration is safe to expose, and say why not.

Run it before deploying, and in CI against the deployment's own environment:

    python backend/tools/preflight.py            # exit 1 on any blocker
    python backend/tools/preflight.py --strict   # exit 1 on warnings too

The one blocker that matters is the combination the whole sandbox chapter is
about: arbitrary code enabled with no container boundary under it.  Everything
else is a warning, because the defaults are tuned for a laptop and a laptop is
the common case.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.config import SETTINGS                     # noqa: E402
from algostudio.plugins.registry import REGISTRY           # noqa: E402
from algostudio.sandbox.docker_sandbox import IMAGE        # noqa: E402

OK, WARN, FAIL = "ok  ", "warn", "FAIL"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="treat warnings as failures")
    args = parser.parse_args()

    lines: list[tuple[str, str]] = []

    # -- the boundary ---------------------------------------------------
    if SETTINGS.allow_arbitrary_code and SETTINGS.sandbox_mode != "docker":
        lines.append((FAIL, (
            "arbitrary code is enabled without the container sandbox. "
            "Set ALGOSTUDIO_SANDBOX=docker, or ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0 "
            "to publish the curated catalogue instead."
        )))
    elif SETTINGS.allow_arbitrary_code:
        lines.append((OK, "arbitrary code enabled, sandbox_mode=docker"))
    else:
        lines.append((OK, "curated mode: bundled algorithms only"))

    if SETTINGS.sandbox_mode == "docker":
        if shutil.which("docker") is None:
            lines.append((FAIL, "sandbox_mode=docker but the docker CLI is not on PATH"))
        elif not _image_present():
            lines.append((FAIL, (
                f"sandbox image {IMAGE} is missing. Build it: "
                "docker build -f backend/Dockerfile.runtime "
                f"-t {IMAGE} backend"
            )))
        else:
            lines.append((OK, f"sandbox image {IMAGE} present"))

    # -- serving --------------------------------------------------------
    if "*" in SETTINGS.cors_origins:
        lines.append((WARN, "CORS allows every origin (ALGOSTUDIO_CORS_ORIGINS)"))
    else:
        lines.append((OK, f"CORS origins: {', '.join(SETTINGS.cors_origins) or 'none'}"))

    dist = ROOT.parent / "frontend" / "dist"
    if dist.is_dir():
        lines.append((OK, "frontend/dist present; the API will serve the SPA"))
    else:
        lines.append((WARN, "frontend/dist missing: the API will serve the API only "
                            "(run: cd frontend && npm run build)"))

    # -- state ----------------------------------------------------------
    try:
        SETTINGS.ensure_dirs()
        probe = SETTINGS.data_dir / ".preflight"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        lines.append((OK, f"data directory writable: {SETTINGS.data_dir}"))
    except OSError as exc:
        lines.append((FAIL, f"data directory not writable: {SETTINGS.data_dir} ({exc})"))

    if SETTINGS.retention_days <= 0:
        lines.append((WARN, "retention disabled; recordings accumulate forever"))
    else:
        lines.append((OK, f"retention: {SETTINGS.retention_days} days"))

    # -- content --------------------------------------------------------
    reports = REGISTRY.reports()
    broken = [pid for pid, report in reports.items() if not report.ok]
    if broken:
        lines.append((FAIL, f"{len(broken)} plugin(s) fail validation: "
                            f"{', '.join(sorted(broken)[:5])}"))
    else:
        lines.append((OK, f"{len(reports)} algorithm plugins validate"))

    # -- report ---------------------------------------------------------
    for status, message in lines:
        print(f"[{status}] {message}")
    failures = sum(1 for s, _ in lines if s == FAIL)
    warnings = sum(1 for s, _ in lines if s == WARN)
    print(f"\n{failures} blocker(s), {warnings} warning(s)")
    if failures:
        return 1
    return 1 if (args.strict and warnings) else 0


def _image_present() -> bool:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", IMAGE],
            capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


if __name__ == "__main__":
    raise SystemExit(main())
