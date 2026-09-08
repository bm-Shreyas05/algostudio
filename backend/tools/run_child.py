"""Developer harness: run a program through the sandbox child and print events.

    python tools/run_child.py path/to/prog.py [--granularity standard] [--entry f]

Bypasses the API and the service layer, so it is the fastest way to see what
the transformer and the probes actually produce.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.core.events import Event, summarize  # noqa: E402


def run(source: str, granularity: str = "standard", entry: str | None = None,
        inputs: dict | None = None, stdin: str = "", budget: dict | None = None,
        dump: bool = False) -> tuple[list[Event], dict]:
    job_dir = Path(tempfile.mkdtemp(prefix="algostudio_"))
    job = {
        "source": source,
        "granularity": granularity,
        "entry": entry,
        "inputs": inputs or {},
        "stdin": stdin,
        "budget": budget or {},
    }
    if dump:
        job["dump_instrumented"] = str(job_dir / "instrumented.py")
    (job_dir / "job.json").write_text(json.dumps(job), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", "-B", str(ROOT / "algostudio/runtime/child_main.py"), str(job_dir)],
        capture_output=True,
        text=True,
    )
    if proc.stderr.strip():
        print("[child stderr]", proc.stderr, file=sys.stderr)
    events = [
        Event.from_json(line)
        for line in (job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    result["job_dir"] = str(job_dir)
    if dump:
        print((job_dir / "instrumented.py").read_text(encoding="utf-8"))
        print("=" * 70)
    return events, result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--granularity", default="standard")
    ap.add_argument("--entry", default=None)
    ap.add_argument("--inputs", default=None, help="JSON object")
    ap.add_argument("--dump", action="store_true", help="print instrumented source")
    ap.add_argument("--types", default=None, help="comma-separated filter")
    args = ap.parse_args()

    source = Path(args.path).read_text(encoding="utf-8")
    events, result = run(
        source,
        args.granularity,
        args.entry,
        json.loads(args.inputs) if args.inputs else None,
        dump=args.dump,
    )
    wanted = set(args.types.split(",")) if args.types else None
    for ev in events:
        name = ev.type.value if hasattr(ev.type, "value") else str(ev.type)
        if wanted and name not in wanted:
            continue
        print(f"{ev.id:>5} L{ev.line:<4} d{ev.depth} {name:<22} {summarize(ev)}")
    print("-" * 70)
    print(json.dumps({k: v for k, v in result.items() if k != "job_dir"}, indent=1))
    print("job dir:", result["job_dir"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
