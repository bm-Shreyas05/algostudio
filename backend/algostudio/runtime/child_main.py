"""Sandbox child entrypoint.

Usage::

    python -I -B child_main.py <job_dir>

``<job_dir>/job.json`` describes what to run; the child writes ``events.jsonl``
and ``result.json`` into the same directory and exits.

Instrumentation happens **here**, not in the parent.  The alternative --
transforming in the parent and shipping either a marshalled code object or
unparsed source -- either couples the two processes to one interpreter version
or risks an unparse round-trip changing the program.  Transforming from the
original source in the child keeps the compiled code object's line numbers
identical to the user's, which is what makes tracebacks and source highlighting
correct.  The transformer's only dependencies are ``ast`` and ``algostudio.core``,
and it runs to completion *before* any user code executes.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND = _HERE.parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from algostudio.core.errors import ExecutionBudgetExceeded  # noqa: E402
from algostudio.core.events import EventType  # noqa: E402
from algostudio.languages.python.transformer import instrument  # noqa: E402
from algostudio.runtime import policy, probe  # noqa: E402
from algostudio.runtime.recorder import (  # noqa: E402
    Budget, OutputProxy, Recorder, StdinProxy,
)
from algostudio.runtime.semantic import SemanticAPI  # noqa: E402

USER_FILENAME = "<algostudio:main>"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: child_main.py <job_dir>", file=sys.stderr)
        return 2
    job_dir = Path(argv[1])
    job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))

    real_stdout, real_stderr = sys.stdout, sys.stderr
    events_path = job_dir / "events.jsonl"
    status = "ok"
    error: dict[str, object] | None = None

    with events_path.open("w", encoding="utf-8", newline="\n") as sink:
        budget = Budget(**job.get("budget", {}))
        recorder = Recorder(sink, budget, job.get("granularity", "standard"))
        try:
            status, error = _run(job, recorder)
        except BaseException as exc:  # last-resort guard: never lose the trace
            status = "internal_error"
            error = {"type": type(exc).__name__, "message": str(exc)}
            traceback.print_exc(file=real_stderr)
        finally:
            sys.stdout, sys.stderr = real_stdout, real_stderr
            try:
                recorder.program_finished(status, {"error": error} if error else None)
            except Exception:  # pragma: no cover
                pass

    (job_dir / "result.json").write_text(
        json.dumps(
            {
                "status": status,
                "error": error,
                "event_count": recorder.n,
                "counters": recorder.counters,
                "duration_ms": round(recorder.elapsed * 1000, 3),
                "heap_objects": recorder.encoder.object_count,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    return 0 if status == "ok" else 1


def _run(job: dict, recorder: Recorder) -> tuple[str, dict | None]:
    source: str = job["source"]
    granularity: str = job.get("granularity", "standard")

    # --- instrument (before any user code runs, and before hardening) -------
    tree, result = instrument(source, granularity, filename=USER_FILENAME)
    code = compile(tree, USER_FILENAME, "exec")
    if job.get("dump_instrumented"):
        try:
            import ast as _ast

            Path(job["dump_instrumented"]).write_text(
                _ast.unparse(tree), encoding="utf-8"
            )
        except Exception:  # pragma: no cover - debugging aid only
            pass

    # --- harden -------------------------------------------------------------
    stdin_proxy = StdinProxy(recorder, job.get("stdin", ""))
    policy.install(job.get("allowed_modules") or None)
    safe_builtins = policy.build_safe_builtins(stdin_proxy=stdin_proxy)

    probe_ns = probe.install(recorder)
    algo = SemanticAPI(recorder)

    user_globals: dict[str, object] = {
        "__name__": "__main__",
        "__file__": USER_FILENAME,
        "__doc__": None,
        "__builtins__": safe_builtins,
        "algo": algo,
        **probe_ns,
    }

    sys.stdout = OutputProxy(recorder, "stdout")   # type: ignore[assignment]
    sys.stderr = OutputProxy(recorder, "stderr")   # type: ignore[assignment]

    recorder.program_started(
        {
            "language": "python",
            "granularity": granularity,
            "schema_version": 1,
            "entry": job.get("entry"),
            "python": "%d.%d" % sys.version_info[:2],
            "skips": [
                {"line": s.line, "construct": s.construct, "reason": s.reason}
                for s in result.skips
            ],
        }
    )

    try:
        exec(code, user_globals)
        entry = job.get("entry")
        if entry:
            fn = user_globals.get(entry)
            if not callable(fn):
                raise NameError(f"entry point {entry!r} is not defined in the program")
            inputs = job.get("inputs") or {}
            value = fn(**inputs)
            recorder.emit(
                EventType.ALGORITHM_EVENT,
                {"name": "result", "args": {"value": recorder.enc(value)}},
                0,
                meta={"origin": "harness"},
            )
    except ExecutionBudgetExceeded as exc:
        return "budget_exceeded", {"type": "ExecutionBudgetExceeded", "message": exc.reason}
    except SystemExit:
        return "ok", None
    except RecursionError as exc:
        _record_exception(recorder, exc)
        return "error", _describe(exc)
    except BaseException as exc:
        _record_exception(recorder, exc)
        return "error", _describe(exc)
    return "ok", None


def _record_exception(recorder: Recorder, exc: BaseException) -> None:
    line = _user_line(exc)
    try:
        recorder.emit(
            EventType.EXCEPTION_RAISED,
            {
                "exc_type": type(exc).__name__,
                "message": str(exc),
                "uncaught": True,
                "traceback_lines": _user_lines(exc),
            },
            line,
        )
    except ExecutionBudgetExceeded:
        pass


def _user_lines(exc: BaseException) -> list[int]:
    lines: list[int] = []
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == USER_FILENAME:
            lines.append(tb.tb_lineno)
        tb = tb.tb_next
    return lines


def _user_line(exc: BaseException) -> int:
    lines = _user_lines(exc)
    return lines[-1] if lines else 0


def _describe(exc: BaseException) -> dict[str, object]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "line": _user_line(exc),
        "traceback": _user_lines(exc),
    }


if __name__ == "__main__":
    os.environ.setdefault("PYTHONHASHSEED", "0")
    sys.exit(main(sys.argv))
