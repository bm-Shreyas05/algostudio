"""Developer harness for the time-travel invariants.

Asserts, for a program, that:
  * ``state_at(n)`` equals a full forward replay to n, for every n
  * walking backwards with ``step_back`` reproduces every earlier state
  * ``seek`` from arbitrary positions lands on the same state

These are the mechanised forms of INV-3 and objectives O4/O5.  The pytest
suite runs the same checks over the whole fixture corpus; this script is for
looking at one program while developing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.state import reducer                      # noqa: E402
from algostudio.state.timeline import Timeline, normalize_ids  # noqa: E402
from tools.run_child import run                           # noqa: E402


def canonical(state) -> str:
    return json.dumps(state.to_dict(), sort_keys=True, default=str)


def check(source: str, granularity: str = "standard", entry=None, inputs=None):
    events, result = run(source, granularity, entry, inputs)
    normalize_ids(events)
    tl = Timeline(events)
    problems: list[str] = []

    reference: list[str] = []
    state = tl.initial()
    for ev in events:
        reducer.apply(state, ev)
        reference.append(canonical(state))

    for i in range(len(events)):
        if canonical(tl.state_at(i)) != reference[i]:
            problems.append(f"state_at({i}) != forward replay")
            break

    s = tl.state_at(tl.last_step)
    for i in range(tl.last_step, -1, -1):
        if canonical(s) != reference[i]:
            problems.append(f"step_back reached step {i} with the wrong state")
            break
        s = tl.step_back(s)

    for target in (0, len(events) // 3, len(events) // 2, tl.last_step, 1):
        s = tl.state_at(tl.last_step)
        s = tl.seek(s, target)
        if canonical(s) != reference[target]:
            problems.append(f"seek(-> {target}) != reference")

    return events, result, problems


def main() -> int:
    paths = sys.argv[1:] or [
        str(p) for p in sorted((ROOT / "tests/fixtures").rglob("*.py"))
    ]
    failed = 0
    for path in paths:
        source = Path(path).read_text(encoding="utf-8")
        events, result, problems = check(source)
        name = Path(path).name
        if problems:
            failed += 1
            print(f"FAIL {name:<28} {result['status']:<16} " + "; ".join(problems))
        else:
            print(f"ok   {name:<28} {result['status']:<16} {len(events):>6} events")
    print("-" * 60)
    print(f"{len(paths) - failed}/{len(paths)} programs satisfy the time-travel invariants")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
