"""FastAPI application.

Thin by design: routers translate DTOs to service calls and back.  All business
logic lives in ``services/``, so the engine is fully usable from a script, a
test, or the benchmark harness without starting a server.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..ai import modes as ai_modes
from ..analysis import static as static_analysis
from ..config import SETTINGS
from ..core.errors import AlgoStudioError, ArbitraryCodeDisabledError
from ..inputs import generators
from ..languages.registry import available as available_languages, get as get_frontend
from ..plugins.registry import REGISTRY as PLUGINS
from ..services.ai_service import AIService
from ..services.benchmark_service import BenchmarkService
from ..services.execution_service import ExecutionService, RunRequest
from .schemas import (
    AnalyzeRequest, AskAI, BenchmarkRequest, CreateExecution, GenerateInput,
    RunAlgorithm, SaveSession,
)

API = "/api/v1"


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    for warning in SETTINGS.deployment_warnings():
        print(f"[algostudio] WARNING: {warning}", flush=True)
    # Recordings are regenerable, so expiry is a sweep at boot rather than a
    # scheduled job: a long-lived server should also run tools/gc.py from cron
    # (deploy/algostudio-gc.timer), but a restart must never leave last
    # month's runs on disk.
    removed = app.state.executions.purge_expired()
    if removed:
        print(f"[algostudio] retention: removed {removed} expired execution(s)",
              flush=True)
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="AlgoStudio",
        version="1.0.0",
        description=(
            "Universal event-driven program execution and visualization platform."
        ),
        lifespan=_lifespan,
    )
    # "none" means the SPA is served from this same process, so there is no
    # cross-origin caller to allow.  The development default is a wildcard
    # because the Vite dev server is a different origin.
    origins = [o for o in SETTINGS.cors_origins if o.lower() != "none"]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    executions = ExecutionService()
    ai = AIService(executions)
    benchmarks = BenchmarkService(executions)
    limiter = RateLimiter()
    app.state.executions = executions
    app.state.ai = ai
    app.state.benchmarks = benchmarks

    # ------------------------------------------------------------------
    @app.exception_handler(AlgoStudioError)
    async def _engine_error(request: Request, exc: AlgoStudioError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_problem(),
            media_type="application/problem+json",
        )

    # ---------------------------------------------------------------- meta
    @app.get(f"{API}/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "sandbox_mode": SETTINGS.sandbox_mode,
            "allow_arbitrary_code": SETTINGS.allow_arbitrary_code,
            "languages": available_languages(),
            "ai": ai.provider_status(),
            "limits": {
                "max_events": SETTINGS.max_events,
                "max_seconds": SETTINGS.max_seconds,
                "max_source_bytes": SETTINGS.max_source_bytes,
            },
            "warnings": SETTINGS.deployment_warnings(),
        }

    @app.get(f"{API}/ai/modes")
    def ai_modes_catalog() -> dict[str, Any]:
        return {"modes": ai_modes.catalog(), "provider": ai.provider_status()}

    # ---------------------------------------------------------- executions
    @app.post(f"{API}/executions", status_code=201)
    def create_execution(body: CreateExecution, request: Request) -> dict[str, Any]:
        _require_arbitrary_code()
        limiter.check(request, "run", SETTINGS.rate_limit_runs_per_minute)
        result = executions.run(
            RunRequest(
                source=body.source,
                language=body.language,
                granularity=body.granularity,
                inputs=body.inputs,
                entry=body.entry,
                stdin=body.stdin,
                strict_capabilities=body.options.strict_capabilities,
                lifters=body.options.lifters,
                max_seconds=body.options.max_seconds,
                max_events=body.options.max_events,
                use_cache=body.options.use_cache,
            )
        )
        return {
            "execution_id": result.execution_id,
            "status": result.status,
            "cached": result.cached,
            "event_count": result.event_count,
            "capability_report": result.capability_report,
            "error": result.error,
            "wall_ms": round(result.wall_ms, 2),
            "ws": f"/ws/executions/{result.execution_id}",
        }

    @app.get(f"{API}/executions")
    def list_executions(limit: int = Query(30, ge=1, le=100),
                        offset: int = Query(0, ge=0)) -> dict[str, Any]:
        return {"executions": executions.db.list_executions(limit, offset)}

    @app.get(f"{API}/executions/{{execution_id}}")
    def get_execution(execution_id: str) -> dict[str, Any]:
        return executions.summary(execution_id)

    @app.delete(f"{API}/executions/{{execution_id}}", status_code=204)
    def delete_execution(execution_id: str) -> None:
        executions.delete(execution_id)

    @app.get(f"{API}/executions/{{execution_id}}/events")
    def get_events(execution_id: str,
                   offset: int = Query(0, ge=0),
                   limit: int = Query(2000, ge=1, le=20000),
                   types: str | None = None,
                   frame: int | None = None,
                   line: int | None = None) -> dict[str, Any]:
        return executions.events(
            execution_id, offset, limit,
            set(types.split(",")) if types else None, frame, line,
        )

    @app.get(f"{API}/executions/{{execution_id}}/state")
    def get_state(execution_id: str, step: int = Query(0, ge=-1),
                  include_heap: bool = True) -> dict[str, Any]:
        return executions.state_at(execution_id, step).to_dict(include_heap)

    @app.get(f"{API}/executions/{{execution_id}}/views")
    def get_views(execution_id: str, step: int = Query(0, ge=-1)) -> dict[str, Any]:
        return {"plan": executions.views(execution_id, step)}

    @app.get(f"{API}/executions/{{execution_id}}/analytics")
    def get_analytics(execution_id: str) -> dict[str, Any]:
        return executions.analytics(execution_id)

    @app.get(f"{API}/executions/{{execution_id}}/source-map")
    def get_source_map(execution_id: str) -> dict[str, Any]:
        meta = executions.meta(execution_id)
        return {
            "source_map": meta.get("source_map", {}),
            "structure": meta.get("structure", {}),
        }

    @app.post(f"{API}/executions/{{execution_id}}/ai")
    def ask_ai(execution_id: str, body: AskAI, request: Request) -> dict[str, Any]:
        limiter.check(request, "ai", SETTINGS.rate_limit_ai_per_minute)
        return ai.ask(
            execution_id, body.step, body.mode, body.question,
            body.focus, body.use_cache,
        )

    # ------------------------------------------------------------ analysis
    @app.post(f"{API}/analyze")
    def analyze(body: AnalyzeRequest) -> dict[str, Any]:
        # Analysis does not execute anything, but it does instrument source a
        # visitor supplied, and in curated mode the editor is hidden anyway.
        _require_arbitrary_code()
        result = get_frontend(body.language).analyze(body.source)
        return {
            "language": body.language,
            "capability_report": result.capability.to_dict(),
            "source_map": result.source_map.to_dict(),
            "analysis": static_analysis.analyze(result.program, body.source),
        }

    # ---------------------------------------------------------- algorithms
    @app.get(f"{API}/algorithms")
    def list_algorithms() -> dict[str, Any]:
        return {
            "algorithms": [p.to_dict() for p in PLUGINS.all()],
            "problems": {
                pid: report.problems
                for pid, report in PLUGINS.reports().items() if not report.ok
            },
        }

    @app.get(f"{API}/algorithms/{{algorithm_id}}")
    def get_algorithm(algorithm_id: str) -> dict[str, Any]:
        return PLUGINS.get(algorithm_id).to_dict(include_source=True)

    @app.post(f"{API}/algorithms/{{algorithm_id}}/run", status_code=201)
    def run_algorithm(algorithm_id: str, body: RunAlgorithm,
                      request: Request) -> dict[str, Any]:
        limiter.check(request, "run", SETTINGS.rate_limit_runs_per_minute)
        result = executions.run_algorithm(
            algorithm_id, body.inputs, body.granularity,
            strict_capabilities=body.options.strict_capabilities,
            lifters=body.options.lifters,
            max_seconds=body.options.max_seconds,
            max_events=body.options.max_events,
            use_cache=body.options.use_cache,
        )
        return {
            "execution_id": result.execution_id,
            "status": result.status,
            "cached": result.cached,
            "event_count": result.event_count,
            "capability_report": result.capability_report,
            "error": result.error,
            "ws": f"/ws/executions/{result.execution_id}",
        }

    # --------------------------------------------------------------- input
    @app.post(f"{API}/inputs/generate")
    def generate_input(body: GenerateInput) -> dict[str, Any]:
        try:
            return generators.generate(body.kind, **body.to_kwargs())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get(f"{API}/inputs/kinds")
    def input_kinds() -> dict[str, Any]:
        return {
            "kinds": ["array", "matrix", "string", "graph", "weighted_graph", "tree"],
            "distributions": list(generators.ARRAY_DISTRIBUTIONS),
            "shapes": list(generators.GRAPH_SHAPES),
        }

    # ----------------------------------------------------------- benchmark
    @app.post(f"{API}/benchmarks", status_code=201)
    def create_benchmark(body: BenchmarkRequest, request: Request) -> dict[str, Any]:
        limiter.check(request, "run", SETTINGS.rate_limit_runs_per_minute)
        result = benchmarks.compare(
            body.algorithms, body.input_spec, body.sizes, body.granularity
        )
        benchmark_id = executions.db.save_benchmark(
            body.name or "comparison", result["input_spec"], result["runs"]
        )
        return {"benchmark_id": benchmark_id, **result}

    @app.get(f"{API}/benchmarks/{{benchmark_id}}")
    def get_benchmark(benchmark_id: str) -> dict[str, Any]:
        record = executions.db.get_benchmark(benchmark_id)
        if record is None:
            raise HTTPException(status_code=404, detail="benchmark not found")
        return record

    # ------------------------------------------------------------ sessions
    @app.post(f"{API}/sessions", status_code=201)
    def save_session(body: SaveSession) -> dict[str, Any]:
        executions.summary(body.execution_id)   # 404 if unknown
        return executions.db.save_session(body.execution_id, body.ui_state)

    @app.get(f"{API}/sessions/{{token}}")
    def load_session(token: str) -> dict[str, Any]:
        record = executions.db.get_session(token)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return record

    # ----------------------------------------------------------- websocket
    @app.websocket("/ws/executions/{execution_id}")
    async def stream(websocket: WebSocket, execution_id: str) -> None:
        """Deliver an execution's events in batches.

        Delivery only -- step, seek and play are client-side, because the client
        already holds the events.  A dropped socket therefore degrades to "no
        live updates", never to "the debugger is stuck", and reconnection needs
        no server-side session state: the client just says where to resume from.
        """
        await websocket.accept()
        try:
            summary = executions.summary(execution_id)
        except AlgoStudioError as exc:
            await websocket.send_json({"v": 1, "type": "error", "seq": 0,
                                       "error": exc.to_problem()})
            await websocket.close()
            return

        seq = 0
        await websocket.send_json({
            "v": 1, "type": "hello", "seq": seq,
            "execution_id": execution_id,
            "status": summary["status"],
            "event_count": summary["event_count"],
            "granularity": summary["granularity"],
        })

        cursor = 0
        try:
            message = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            cursor = max(0, int(message.get("from_event", 0)))
        except Exception:
            cursor = 0

        try:
            while True:
                page = executions.events(execution_id, cursor, 512)
                if not page["events"]:
                    break
                seq += 1
                await websocket.send_json({
                    "v": 1, "type": "events", "seq": seq,
                    "from": cursor, "to": cursor + len(page["events"]),
                    "events": page["events"],
                })
                cursor += len(page["events"])
                await asyncio.sleep(0)
            seq += 1
            await websocket.send_json({
                "v": 1, "type": "finished", "seq": seq,
                "status": summary["status"],
                "event_count": summary["event_count"],
                "analytics_url": f"{API}/executions/{execution_id}/analytics",
                "wall_ms": summary["wall_ms"],
            })
        except WebSocketDisconnect:
            return
        except Exception:
            return

    _mount_frontend(app)
    return app


def _require_arbitrary_code() -> None:
    if not SETTINGS.allow_arbitrary_code:
        raise ArbitraryCodeDisabledError(
            "this deployment runs the bundled algorithm catalogue only; "
            "arbitrary source execution is disabled",
            catalogue=f"{API}/algorithms",
        )


class RateLimiter:
    """Fixed-window per-client limiter.

    Deliberately in-process: this deployment is single-node, and a Redis
    dependency to count requests would be infrastructure for its own sake.
    """

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, request: Request, bucket: str, per_minute: int) -> None:
        client = request.client.host if request.client else "unknown"
        key = (client, bucket)
        now = time.time()
        window = self._hits[key]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= per_minute:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit: {per_minute} {bucket} requests per minute",
                headers={"Retry-After": "60"},
            )
        window.append(now)


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA when it exists, so one process runs the whole demo."""
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")


app = create_app()
