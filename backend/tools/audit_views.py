"""Audit the visualization every algorithm actually produces.

Runs each plugin and inspects the view plan and live annotations at several
points through the run, then flags the ones whose visualization is weak:

  no-views          nothing at all is drawn
  unnamed-primary   the headline card is an anonymous heap ref (h7), which
                    tells a reader nothing
  raw-primary       the fallback "raw JSON" view won, meaning no detector
                    recognised the data
  no-annotations    nothing is highlighted, so the animation has no focus
  graph-no-path     a graph is drawn but no visit annotations, so the
                    traversal order is invisible
  array-no-markers  an array is drawn but no pointer/compare/swap annotations

Run with no arguments for the full table, or pass algorithm ids to check a few.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algostudio.plugins.registry import REGISTRY            # noqa: E402
from algostudio.services.execution_service import ExecutionService  # noqa: E402

SAMPLE_FRACTIONS = tuple(i / 20 for i in range(1, 21))
#: Anything that puts a visible marker on an array or string.
POINTER_KINDS = {
    "pointer", "region", "compare", "swap", "highlight",
    "push", "pop", "enqueue", "dequeue",
}


def audit_one(svc: ExecutionService, plugin_id: str) -> dict:
    result = svc.run_algorithm(plugin_id, granularity="standard")
    timeline = svc.timeline(result.execution_id)
    last = timeline.last_step
    plugin = REGISTRY.get(plugin_id)

    kinds: Counter[str] = Counter()
    best_plan = None
    primary_views: Counter[str] = Counter()
    # Does a local ever point into a drawn structure?  That is what makes the
    # tree and graph cursors work, and it needs no annotations at all -- so it
    # has to be sampled across the run, not just at the end where every frame
    # has returned.
    refs_into_structure = False

    for fraction in SAMPLE_FRACTIONS:
        step = max(0, int(last * fraction))
        state = svc.state_at(result.execution_id, step)
        for ann in state.live_annotations():
            kinds[ann.kind] += 1
        plan = svc.views(result.execution_id, step)
        # Synthetic plans (strings, scalar frames) carry their own record and
        # are deliberately absent from the heap.
        visible = [
            p for p in plan
            if p["ref"] in state.heap or p.get("props", {}).get("record")
        ]
        if visible:
            primary_views[visible[0]["view"]] += 1
            if best_plan is None or len(visible) > len(best_plan):
                best_plan = visible
        if not refs_into_structure:
            refs_into_structure = any(
                isinstance(v, dict) and v.get("k") == "ref" and v.get("r") in state.heap
                for v in state.frames[-1].locals.values()
            )

    plan = best_plan or []
    top = plan[0] if plan else None
    views = {p["view"] for p in plan[:6]}

    flags = []
    if not plan:
        flags.append("no-views")
    else:
        if not top["name"]:
            flags.append("unnamed-primary")
        if top["view"] == "value":
            flags.append("raw-primary")
    if not kinds:
        flags.append("no-annotations")

    # Judge only the *primary* view: a secondary result list with no markers is
    # not a broken visualization.
    primary_view = top["view"] if top else None
    if primary_view == "graph" and not (
        kinds.get("visit") or kinds.get("relax") or kinds.get("nodevalue")
    ):
        flags.append("graph-no-path")
    if primary_view == "tree" and not (
        kinds.get("visit") or kinds.get("mark") or refs_into_structure
    ):
        flags.append("tree-no-path")
    if primary_view in ("array", "string") and not any(
        kinds.get(k) for k in POINTER_KINDS
    ):
        flags.append("array-no-markers")

    return {
        "id": plugin_id,
        "category": plugin.category,
        "events": result.event_count,
        "status": result.status,
        "top": f"{top['name'] or top['ref']}:{top['view']}" if top else "-",
        "cards": len(plan),
        "annotations": dict(kinds),
        "flags": flags,
    }


def main() -> int:
    svc = ExecutionService()
    wanted = sys.argv[1:] or sorted(REGISTRY.discover())
    rows = []
    for plugin_id in wanted:
        try:
            rows.append(audit_one(svc, plugin_id))
        except Exception as exc:  # pragma: no cover - report, never abort
            rows.append({
                "id": plugin_id, "category": "?", "events": 0, "status": "EXC",
                "top": "-", "cards": 0, "annotations": {},
                "flags": [f"exception:{type(exc).__name__}:{exc}"],
            })

    rows.sort(key=lambda r: (not r["flags"], r["category"], r["id"]))
    print(f"{'algorithm':<30}{'category':<22}{'top view':<26}{'cards':>6}  flags / annotations")
    print("-" * 118)
    problems = 0
    for row in rows:
        if row["flags"]:
            problems += 1
        note = ", ".join(row["flags"]) if row["flags"] else ", ".join(
            f"{k}×{v}" for k, v in sorted(row["annotations"].items())
        ) or "(none)"
        print(f"{row['id']:<30}{row['category']:<22}{row['top']:<26}{row['cards']:>6}  {note}")
    print("-" * 118)
    print(f"{len(rows) - problems}/{len(rows)} clean · {problems} flagged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
