"""FastAPI application.

Thin by design: routers translate DTOs to service calls and back.  All business
logic lives in ``services/``, so the engine is fully usable from a script, a
test, or the benchmark harness without starting a server.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
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
    # HTML, JSON and the event stream are all highly compressible text, and the
    # event stream is by far the largest thing this API sends -- a 445-event
    # recording is mostly repeated keys.  500 bytes is the floor below which
    # the header overhead is not worth it.
    app.add_middleware(GZipMiddleware, minimum_size=500)

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
    def health(request: Request) -> dict[str, Any]:
        warnings = SETTINGS.deployment_warnings()
        warnings += _canonical_warnings(request)
        return {
            "status": "ok",
            "sandbox_mode": SETTINGS.sandbox_mode,
            "allow_arbitrary_code": SETTINGS.allow_arbitrary_code,
            "canonical_origin": _baked_origin(),
            "languages": available_languages(),
            "ai": ai.provider_status(),
            "limits": {
                "max_events": SETTINGS.max_events,
                "max_seconds": SETTINGS.max_seconds,
                "max_source_bytes": SETTINGS.max_source_bytes,
            },
            "warnings": warnings,
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


#: Clean URL -> file in the built site.  Mirrors PAGES in vite.config.ts; the
#: sitemap is generated from that list, so if these two ever disagree the
#: sitemap advertises a URL that 404s.  tools/check_site.py asserts they match.
ROUTES = {
    "/": "index.html",
    "/app": "app.html",
    "/faq": "faq.html",
    "/privacy": "privacy.html",
    "/terms": "terms.html",
}

#: Served from the site root under their own names.
ROOT_FILES = (
    "robots.txt", "sitemap.xml", "favicon.ico", "favicon.svg", "og.png",
    "site.webmanifest", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
)

#: Hashed asset names change whenever their content does, so they can be
#: cached forever.  HTML must not be, or a deploy is invisible to returning
#: visitors until their cache expires.
IMMUTABLE = "public, max-age=31536000, immutable"
REVALIDATE = "public, max-age=0, must-revalidate"
ROOT_FILE_CACHE = "public, max-age=86400"


@lru_cache(maxsize=1)
def _baked_origin() -> str | None:
    """The origin compiled into the built pages' canonical tags.

    Absolute URLs have to be chosen at build time, which means a build can be
    deployed somewhere other than the origin it was told about. That mistake
    is completely silent -- the site renders perfectly while telling search
    engines the real copy lives at an origin nobody owns -- so it is read back
    out of the artefact and checked, rather than trusted.
    """
    index = Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"
    try:
        head = index.read_text(encoding="utf-8")[:8192]
    except OSError:
        return None
    match = re.search(r'rel="canonical"\s+href="(https?://[^/"]+)', head)
    return match.group(1) if match else None


def _canonical_warnings(request: Request) -> list[str]:
    """Flag a build whose canonical origin is not where it is being served."""
    baked = _baked_origin()
    if not baked:
        return []
    # Behind Render's proxy the request URL is already rewritten to the public
    # host, but honour the forwarded headers where they are present.
    host = request.headers.get("x-forwarded-host") or request.url.hostname or ""
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    if not host:
        return []
    served = f"{scheme}://{host.split(',')[0].strip()}"
    if urlsplit(served).hostname in ("localhost", "127.0.0.1", "0.0.0.0"):
        return []
    if served.rstrip("/") == baked.rstrip("/"):
        return []
    return [
        f"this build's canonical URLs point at {baked}, but it is being served "
        f"from {served}. Search engines will attribute these pages to the wrong "
        f"origin. Rebuild with --build-arg VITE_SITE_URL={served}"
    ]


class _ImmutableStatic(StaticFiles):
    """Static files whose name contains their content hash.

    Vite writes ``app-176iMQdH.js``; a change to the file changes the name, so
    the old name can never point at new content and a year-long cache is safe.
    Without this the browser revalidates every asset on every visit, which on a
    cold free-tier instance is the difference between an instant second load
    and another round trip per file.
    """

    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = IMMUTABLE
        return response


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built site: clean URLs, real 404s, cache headers.

    One process serves the API and the site from a single origin, which is why
    no CORS grant is needed in production and why there is no separate static
    host to keep in sync.  When ``frontend/dist`` is absent -- a backend-only
    checkout, or before ``npm run build`` -- none of this is registered and the
    API behaves exactly as it did before.
    """
    dist = Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if not dist.is_dir():
        return

    def page(filename: str, status: int = 200) -> FileResponse:
        return FileResponse(
            dist / filename,
            status_code=status,
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": REVALIDATE},
        )

    # Content-hashed bundles.  Mounted before the catch-all so it wins.
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", _ImmutableStatic(directory=str(assets)), name="assets")

    for url, filename in ROUTES.items():
        if not (dist / filename).is_file():
            continue

        def make(filename: str = filename):
            def handler() -> FileResponse:
                return page(filename)
            return handler

        app.get(url, include_in_schema=False)(make())

        # /app.html and /app would otherwise be two URLs for one page, which
        # splits ranking signals.  The canonical tag says which one counts;
        # this makes the other one stop existing.
        if url != "/":
            app.get(f"/{filename}", include_in_schema=False)(
                lambda url=url: RedirectResponse(url, status_code=301)
            )

    for name in ROOT_FILES:
        if not (dist / name).is_file():
            continue

        def make_root(name: str = name):
            def handler() -> FileResponse:
                return FileResponse(
                    dist / name, headers={"Cache-Control": ROOT_FILE_CACHE}
                )
            return handler

        app.get(f"/{name}", include_in_schema=False)(make_root())

    @app.get("/{path:path}", include_in_schema=False)
    def not_found(path: str) -> Response:
        """Anything unmatched.

        An API path that reached here is a genuine missing endpoint and must
        stay JSON -- handing a client an HTML error page is how a fetch()
        failure turns into an unreadable parse error.
        """
        if path.startswith(("api/", "ws/")):
            raise HTTPException(status_code=404, detail=f"no such endpoint: /{path}")

        # "/faq/" is a URL people type and link to. FastAPI would normally
        # redirect it to "/faq", but this catch-all matches first and would
        # otherwise turn a working page into a 404.
        trimmed = "/" + path.rstrip("/")
        if path.endswith("/") and trimmed in ROUTES:
            return RedirectResponse(trimmed, status_code=301)

        if (dist / "404.html").is_file():
            return page("404.html", status=404)
        raise HTTPException(status_code=404, detail="not found")


app = create_app()
