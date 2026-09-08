"""Differential semantics check -- the project's most important test.

Runs every fixture twice: once as plain Python, once through the instrumented
pipeline.  Standard output and the exception type must match exactly.

If this fails, the transformer has changed the meaning of a program, and every
event, state, visualization and AI explanation built on top of it is describing
something the user did not write.  That is strictly worse than a crash, because
it is invisible.  So this is a merge gate, not a nice-to-have.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.core.events import EventType  # noqa: E402
from tools.run_child import run               # noqa: E402

#: Fixtures that are *expected* to hit a budget or a policy denial, so their
#: native and instrumented behaviour legitimately differ.
EXPECTED_DIVERGENT = {
    "infinite_loop.py",     # native never terminates; instrumented stops at the budget
    "deep_recursion.py",    # different recursion caps
    "big_output.py",        # output is truncated at the budget
    "import_os.py",         # denied by the import policy
    "file_access.py",       # open() is removed from builtins
}


def native_run(path: Path, timeout: float = 5.0) -> tuple[str, str]:
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-B", str(path)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT"
    err = ""
    if proc.returncode != 0:
        last = [ln for ln in proc.stderr.strip().splitlines() if ln.strip()]
        if last:
            err = last[-1].split(":")[0].strip()
    return proc.stdout, err


def instrumented_run(source: str, granularity: str = "standard") -> tuple[str, str]:
    events, result = run(source, granularity, budget={"max_events": 60000})
    out = "".join(
        e.payload.get("text", "")
        for e in events
        if e.type == EventType.STDOUT_WRITE
    )
    err = ""
    if result.get("error"):
        err = str(result["error"].get("type", ""))
    return out, err


def main() -> int:
    fixtures = sorted((ROOT / "tests" / "fixtures").rglob("*.py"))
    granularities = sys.argv[1:] or ["standard"]
    failures = 0
    skipped = 0
    for granularity in granularities:
        print(f"=== granularity: {granularity} ===")
        for path in fixtures:
            name = path.name
            if name in EXPECTED_DIVERGENT:
                skipped += 1
                print(f"skip {name:<26} (divergence is expected and documented)")
                continue
            expected_out, expected_err = native_run(path)
            actual_out, actual_err = instrumented_run(
                path.read_text(encoding="utf-8"), granularity
            )
            if expected_out != actual_out or expected_err != actual_err:
                failures += 1
                print(f"FAIL {name}")
                if expected_out != actual_out:
                    print(f"     stdout native      : {expected_out[:200]!r}")
                    print(f"     stdout instrumented: {actual_out[:200]!r}")
                if expected_err != actual_err:
                    print(f"     error  native={expected_err!r} instrumented={actual_err!r}")
            else:
                print(f"ok   {name:<26} {len(actual_out):>5} bytes out"
                      + (f"  raises {actual_err}" if actual_err else ""))
    print("-" * 62)
    total = len(fixtures) * len(granularities)
    print(f"{total - failures - skipped} matched, {failures} failed, {skipped} skipped")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
