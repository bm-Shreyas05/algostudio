"""The same pipeline ``ExecutionService`` runs, without the server.

    source -> analyse -> instrument+execute -> lift -> timeline -> views

Deliberately built on ``runtime/child_main.py`` rather than reimplementing
execution. That module is what the sandbox child runs on the server, and
docs/21-pyodide-spike.md established that it produces a byte-identical event
stream under Pyodide for 49 of 51 fixtures. Calling anything else here would
throw that guarantee away -- and a browser that produced a *slightly* different
stream would be worse than one that plainly refused, because every claim about
time travel and view resolution is a claim about the stream being faithful.

The three differences from the server, all forced and all bounded:

* no sandbox layer -- the tab is the boundary (see the package docstring);
* no database -- one execution is held in memory and replaced by the next;
* no cache -- there is no second user to share a recording with.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ..analytics import metrics
from ..core.errors import CapabilityReport
from ..languages.registry import get as get_frontend
from ..lifters.pipeline import LifterPipeline
from ..runtime import child_main
from ..shapes.resolver import ViewResolver
from ..state.timeline import Timeline, normalize_ids
from ..store import eventlog

#: Matches the server default so a program behaves the same in both places.
CHECKPOINT_INTERVAL = 64

#: Budgets. Lower than the server's, because the cost of getting these wrong is
#: the visitor's own tab locking up rather than a shared instance degrading --
#: which is more visible to them and less recoverable.
DEFAULT_BUDGET = {
    "max_events": 150_000,
    "max_seconds": 15,
    "max_output_bytes": 1 << 20,
    "max_recursion": 200,
    "max_heap_objects": 50_000,
}

_JOB_DIR = Path("/algostudio-job")


class _Session:
    """One execution, held until the next one replaces it."""

    __slots__ = ("timeline", "analytics", "meta", "resolver")

    def __init__(self, timeline: Timeline, analytics: dict, meta: dict) -> None:
        self.timeline = timeline
        self.analytics = analytics
        self.meta = meta
        self.resolver = ViewResolver()


_current: _Session | None = None


def run(source: str, granularity: str = "standard", lifters: bool = True,
        stdin: str = "", budget: dict[str, Any] | None = None) -> str:
    """Execute ``source`` and keep the result for ``views``/``analytics``.

    Returns a JSON string rather than a dict because everything crossing the
    Pyodide boundary is serialised anyway, and doing it here keeps one
    conversion in one place instead of relying on the proxy's coercion rules.
    """
    global _current
    started = time.perf_counter()

    # -- analyse (before executing anything) ------------------------------
    frontend = get_frontend("python")
    analysis = frontend.analyze(source)
    capability: CapabilityReport = analysis.capability
    if capability.blocking:
        issue = capability.blocking[0]
        return json.dumps({
            "status": "unsupported",
            "error": {"type": "UnsupportedConstruct", "message": issue.message,
                      "line": issue.line},
            "capability_report": capability.to_dict(),
            "events": [], "event_count": 0,
        })

    # -- execute ----------------------------------------------------------
    job_dir = _JOB_DIR
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "events.jsonl").write_text("", encoding="utf-8")
    (job_dir / "job.json").write_text(json.dumps({
        "language": "python", "source": source, "inputs": {},
        "granularity": granularity, "entry": None, "stdin": stdin,
        "budget": {**DEFAULT_BUDGET, **(budget or {})},
        "allowed_modules": None,
    }), encoding="utf-8")

    child_main.main(["child_main.py", str(job_dir)])
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    wall_ms = (time.perf_counter() - started) * 1000.0

    # -- lift, normalise, reduce -------------------------------------------
    raw = eventlog.read_raw(job_dir / "events.jsonl")
    events = LifterPipeline().process(raw) if lifters else list(raw)
    normalize_ids(events)

    timeline = Timeline(events, CHECKPOINT_INTERVAL)
    computed = metrics.compute(events)
    computed.duration_ms = computed.duration_ms or wall_ms

    meta_dict = {
        "language": "python",
        "granularity": granularity,
        "source": source,
        "source_map": analysis.source_map.to_dict(),
        "structure": analysis.structure,
        "capability_report": capability.to_dict(),
        "lifters": lifters,
        "engine": "browser",
    }
    _current = _Session(timeline, computed.to_dict(), meta_dict)

    return json.dumps({
        "status": result.get("status", "internal_error"),
        "error": result.get("error"),
        "capability_report": capability.to_dict(),
        "event_count": len(events),
        "wall_ms": round(wall_ms, 2),
        "last_step": timeline.last_step,
        # The UI's TypeScript reducer consumes these directly, exactly as it
        # does the ones the HTTP API returns.
        "events": [e.to_dict() for e in events],
        "analytics": _current.analytics,
        "meta": meta_dict,
    })


def views(step: int) -> str:
    """The view plan at ``step``, resolved the way the server resolves it."""
    if _current is None:
        return json.dumps([])
    timeline = _current.timeline
    state = timeline.state_at(step)
    # Resolved against the FINAL heap and applied to every step, so an empty
    # `visited = set()` renders as a set from step 0 rather than popping into
    # existence when it happens to fill. Same reasoning as the server.
    final = timeline.state_at(timeline.last_step)
    final.step = state.step
    final.counters = state.counters
    plans = _current.resolver.resolve(final, [], current=state)
    return json.dumps([p.to_dict() for p in plans])


def analytics() -> str:
    return json.dumps(_current.analytics if _current else {})


def meta() -> str:
    return json.dumps(_current.meta if _current else {})
