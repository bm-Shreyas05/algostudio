"""Produce the native ground truth the Pyodide harness is checked against.

For every fixture, run the *unmodified* sandbox child entrypoint, normalise the
event stream, and record a hash of it. The browser then runs the same code over
the same fixtures and must produce the same hashes.

Three fields are excluded from the hash, and only three:

  ``t``            a wall-clock offset, different on every run of anything
  ``duration_ms``  the same thing again, in PROGRAM_FINISHED
  ``python``       the interpreter version in PROGRAM_STARTED, because Pyodide
                   ships a different CPython than the server does

Everything else -- event order, ids, frames, depths, payloads -- has to match
exactly, because the whole architecture rests on the claim that the event
stream is a faithful record of the program. A browser that produced a
*slightly* different stream would be worse than one that failed outright.

    python backend/tools/make_pyodide_fixtures.py <output-dir>
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Set iteration order is part of the event stream -- a BFS visits `visited` in
# whatever order the set yields -- so the stream is only reproducible under a
# fixed hash seed. The real sandbox already pins it in limits.clean_env(); this
# generator has to run under the same condition or its "ground truth" is one
# sample from a distribution. The seed has to be set before the interpreter
# starts, hence the re-exec.
if os.environ.get("PYTHONHASHSEED") != "0":
    os.environ["PYTHONHASHSEED"] = "0"
    os.execv(sys.executable, [sys.executable, *sys.argv])

FIXTURES = ROOT / "tests" / "fixtures"

#: Small enough to keep a runaway fixture's payload sane, large enough that
#: every terminating fixture finishes well inside it.
BUDGET = {
    "max_events": 20_000,
    "max_seconds": 10,
    "max_output_bytes": 1 << 18,
    "max_recursion": 200,
    "max_heap_objects": 50_000,
}


#: Fields whose value is a clock reading or an interpreter build, not a fact
#: about the program. Everything else must match exactly.
VOLATILE = ("python", "duration_ms")


def normalise(event: dict) -> dict:
    event = {k: v for k, v in event.items() if k != "t"}
    payload = event.get("payload")
    if isinstance(payload, dict):
        event["payload"] = {k: v for k, v in payload.items() if k not in VOLATILE}
    return event


def digest(events: list[dict]) -> str:
    h = hashlib.sha256()
    for event in events:
        h.update(json.dumps(normalise(event), sort_keys=True, separators=(",", ":")).encode())
        h.update(b"\n")
    return h.hexdigest()


def run_native(source: str) -> tuple[dict, list[dict]]:
    from algostudio.runtime import child_main

    job_dir = Path(tempfile.mkdtemp())
    try:
        (job_dir / "job.json").write_text(json.dumps({
            "language": "python", "source": source, "inputs": {},
            "granularity": "standard", "entry": None, "stdin": "",
            "budget": BUDGET, "allowed_modules": None,
        }), encoding="utf-8")
        child_main.main(["child_main.py", str(job_dir)])
        events = [
            json.loads(line)
            for line in (job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
        return result, events
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    cases = []
    for path in sorted(FIXTURES.rglob("*.py")):
        name = path.relative_to(FIXTURES).as_posix()
        source = path.read_text(encoding="utf-8")
        result, events = run_native(source)
        cases.append({
            "name": name,
            "source": source,
            "status": result["status"],
            "event_count": result["event_count"],
            "sha256": digest(events),
        })
        print(f"  {name:<34}{result['status']:<18}{result['event_count']:>7} events")

    (out_dir / "fixtures.json").write_text(
        json.dumps({"budget": BUDGET, "cases": cases}), encoding="utf-8"
    )
    size = (out_dir / "fixtures.json").stat().st_size
    print(f"\n{len(cases)} fixtures -> {out_dir / 'fixtures.json'} ({size/1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
