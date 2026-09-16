# 20 — Deployment

*(Extends deliverables S (sandbox), V (repository), W (roadmap). Written after the MVP was
built, so every claim here is about code that exists.)*

---

## A. The one decision everything else follows from

AlgoStudio executes source code. That single fact determines the deployment, and it admits
exactly two honest answers:

| | What runs | Boundary | Where it can be published |
|---|---|---|---|
| **Curated mode** | the 49 bundled plugins only | none needed — no visitor code is ever executed | anywhere: a free tier, a college server, a small VPS |
| **Full mode** | anything a visitor types | `DockerSandbox`, one container per execution | a host whose Docker daemon you control |

There is no third option. In particular, **"full mode without Docker" is not a deployment,
it is an incident**. `docs/06-sandbox.md` §L states it and the code repeats it: the import
allowlist and builtins denylist in `runtime/policy.py` are defense in depth. CPython cannot
be sandboxed in-process — `__subclasses__` walking, C-level recursion, and the sheer surface
of the builtins make containment a research problem, not a configuration option. The
subprocess sandbox is a *budget and blast-radius* layer: it bounds time, memory, event count
and file descriptors, and it kills the process group. It does not stop a program from
reading the filesystem the API runs on.

Two mechanisms were added so this is enforced rather than merely documented:

- `ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0` makes `POST /executions` and `POST /analyze` return
  `403 arbitrary-code-disabled`. Plugin runs, benchmarks, replay, analytics and the AI tutor
  all keep working. The SPA reads the flag from `/health` and disables its editor, so a
  visitor never types a program only to be refused by the server.
- `tools/preflight.py` exits non-zero on the dangerous combination, and `/health` returns the
  same list in a `warnings` array. `make preflight` is the gate before any deploy.

```bash
make preflight
```

---

## B. What was missing, and now exists

The MVP was runnable but not deployable. This phase closed the gap:

| Artifact | Why it was needed |
|---|---|
| `backend/Dockerfile.api` | `docker-compose.yml` referenced it; it had never been written. Two targets: `api-base` (backend only, for development) and `api` (backend + built SPA). |
| `docker-compose.prod.yml` | The deployable stack: one container, data on a named volume, port bound to loopback. |
| `.env.example` | Every deployment-relevant setting in one commented file. `.env` itself is gitignored. |
| `ALGOSTUDIO_ALLOW_ARBITRARY_CODE` | Curated mode, above. |
| `ALGOSTUDIO_CORS_ORIGINS` | CORS was `allow_origins=["*"]`. It is now a list, and `none` installs no middleware at all — correct for the single-container deployment, where the SPA is same-origin. |
| `ExecutionService.purge_expired()` + `tools/gc.py` | `retention_days` was declared in `config.py` and never read: recordings accumulated forever. Now swept at startup and by a nightly timer. |
| `tools/preflight.py` | Turns "did you remember to…" into an exit code. |
| `deploy/` | Caddyfile, systemd unit, retention timer. |
| `tests/test_deployment.py` | 12 assertions. The load-bearing four: curated mode refuses source, curated mode still runs the catalogue, `none` issues no CORS header, and an expired recording takes its directory with it. |

One real bug surfaced while doing this: the compose dev stack pointed the Vite proxy at
`127.0.0.1:8000`, which *inside the `web` container* is the `web` container. The target is
now `VITE_API_TARGET`, set to `http://api:8000` in compose.

---

## C. Stage 1 — curated public link (recommended first deploy)

**Threat surface: nothing of consequence.** No visitor code executes. What is exposed is a
read-mostly API over recordings the maintainer generated, behind rate limits.

```bash
cp .env.example .env
# in .env:  ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0
#           ALGOSTUDIO_SANDBOX=subprocess
#           ALGOSTUDIO_CORS_ORIGINS=none
make build                       # SPA -> frontend/dist
make preflight                   # must exit 0
cd backend && python -m uvicorn algostudio.api.app:app --host 0.0.0.0 --port 8000
```

One process serves both the API and the SPA (`api/app.py::_mount_frontend`), so this fits any
host that can run a Python process: a free PaaS dyno, a college VM, a Raspberry Pi.

It is also the right mode for the **demo and viva**. A stranger's code is pure downside
there, and the 49 plugins are the thing being shown.

Cost note: the first run of each algorithm executes for real; after that `db.find_cached`
serves it. A demo warms up once and is instant thereafter.

## D. Stage 2 — full mode on a VPS

**This is the mode the project is actually about**, because arbitrary Python is the claim.
It needs a host with a Docker daemon you control: a small VPS, a lab machine, a cloud VM.

```bash
cp .env.example .env
# ALGOSTUDIO_SANDBOX=docker
# ALGOSTUDIO_ALLOW_ARBITRARY_CODE=1
make up                                                    # runtime image, then the stack
docker compose -f docker-compose.prod.yml exec api python backend/tools/preflight.py
```

What holds the boundary, per execution, from `sandbox/docker_sandbox.py`:

`--network none` · `--read-only` rootfs · `--tmpfs /tmp:noexec,nosuid,nodev` ·
`--memory` = `--memory-swap` (no swap escape) · `--cpus 0.5` · `--pids-limit 64` ·
`--cap-drop ALL` · `--security-opt no-new-privileges` · `--user 65534:65534` · exactly one
writable bind mount, at `/job`.

**Stated honestly:** the API container mounts the host's Docker socket in order to spawn
those containers, and socket access is root-equivalent on that host. The isolation is
therefore *between visitor code and the host* — which is the threat being defended against —
but the API process itself is privileged and must be treated as such. That is why the port
binds to `127.0.0.1` with a proxy in front, and why arbitrary code and the socket arrive
together or not at all. A rootless daemon or a dedicated runner VM removes the caveat; both
are out of MVP scope and named in §G.

Second honest cost: container start-up adds **150–400 ms per execution**. Cached runs skip it
entirely. A warm pool is the V2 mitigation already recorded in `docs/06-sandbox.md`.

## E. TLS, supervision, state

```
deploy/Caddyfile              TLS + HTTP/2, automatic certificate, four lines
deploy/algostudio.service     systemd unit for the no-Docker (curated) deployment
deploy/algostudio-gc.timer    nightly tools/gc.py
deploy/algostudio-gc.service
```

The systemd unit hardens the API process itself (`ProtectSystem=strict`, `NoNewPrivileges`,
`ProtectHome`, one `ReadWritePaths`). That is host hygiene, not a sandbox, and the unit says
so in its own header: it is for curated mode only.

**State.** Everything lives under `ALGOSTUDIO_DATA`: `executions/<id>/` (events and
checkpoints) plus `algostudio.db` (SQLite, WAL). Back up that one directory, or accept losing
it — recordings are reproducible from source, so the honest backup policy for a student
project is *none*, and the retention sweep is what keeps the disk finite. A share link to an
expired execution 404s; that is documented behaviour, not a bug.

**Scaling.** Deliberately single-node: the rate limiter counts in-process, SQLite is a file,
the timeline cache is a dict. `docs/01-architecture.md` argues for the modular monolith, and
this is where that argument shows up as an operational property. Horizontal scaling would
need a shared store and a shared limiter, and nothing about the workload justifies it — one
box runs a classroom.

---

## F. Deployment checklist

| # | Check | Command / criterion |
|---|---|---|
| 1 | Engine invariants hold | `make check` — 46 fixtures match native semantics, 51/51 time-travel |
| 2 | Every algorithm visualizes | `make audit` — 48/49 clean (`fast_power` is pure arithmetic; the `scalars` view is the honest answer) |
| 3 | Deployment surface behaves | `make test` — 12 passed |
| 3b | The public site is intact | `make check-site` — 0 failures, 0 warnings |
| 4 | Configuration is safe to expose | `make preflight` — must exit 0 |
| 5 | No secrets in the tree | `.env` gitignored; `.env.example` carries names, never values |
| 6 | SPA built | `make build`, then `frontend/dist` exists |
| 7 | Sandbox image present (full mode only) | `docker image inspect algostudio-runtime:latest` |
| 8 | Health is honest | `GET /api/v1/health` → `"warnings": []` |

---

## G. What is deliberately not done

- **Kubernetes, autoscaling, a message queue.** The brief rules them out and the workload does
  not justify them. One container and a proxy.
- **Multi-tenant accounts.** Sessions are share tokens, not users. Auth would add a credential
  store to a project whose threat model is "someone ran a program".
- **Rootless Docker / gVisor / Firecracker.** Each removes the privileged-socket caveat in §D.
  `sandbox/base.py` is already the seam they slot into — that is exactly why the `Sandbox`
  protocol returns a `SandboxResult` and never leaks how isolation was achieved.
- **Pyodide / WASM — the V3 answer.** Running the instrumented program in the browser removes
  the server threat surface entirely and makes curated-vs-full a non-question: a static deploy
  could run arbitrary code safely, because it would run on the visitor's own machine. Named in
  `docs/13-roadmap-and-scope.md` §X and `docs/15-research-and-evaluation.md` §7. The work is
  real but not small: the transformer is pure Python and the reducer already exists in both
  Python and TypeScript, so both port — but the event log, the checkpoint store and the AI
  grounding all assume a server.

---

## H. One-line summary for the report

> AlgoStudio deploys as a single container serving both API and SPA from one origin, in one of
> two modes: a **curated** mode that executes only the bundled catalogue and can be published
> anywhere, and a **full** mode that executes visitor code inside a per-execution Docker
> container with no network, a read-only rootfs and dropped capabilities. The combination
> "visitor code without a container" is refused by `tools/preflight.py`, because the
> in-process restrictions are defense in depth and not a security boundary.

---

## I. The public site

Deploying meant the project needed a front door. The studio is a tool: it is
useful once you are already there, and it explains nothing to a search engine,
because its homepage was 215 KB of JavaScript that renders an empty IDE.

**Structure.** The studio moved to `/app` and a static landing page took `/`.

| URL | What | Weight |
|---|---|---|
| `/` | Landing page: what it is, how the pipeline works, why it is not an algorithm visualizer, what it does **not** do, the numbers, an FAQ | ~17 KB, zero JavaScript |
| `/app` | The studio (unchanged, plus a mobile layout) | 216 KB JS, split into app + react chunks |
| `/faq` | Ten questions with matching `FAQPage` structured data | zero JavaScript |
| `/privacy`, `/terms` | Written from what the code does, not from a template | zero JavaScript |
| `/404` | Real 404 status, `noindex`, links back | zero JavaScript |

The static pages carry no JavaScript at all, and their CSS is inlined into the
HTML at build time, so each is a single request that paints immediately. That
matters more than usual here: a free instance sleeps, and the first visitor
pays a cold start before any byte is served.

**Generated, not maintained.** `robots.txt` and `sitemap.xml` are emitted by a
Vite plugin from the same `PAGES` list that defines the build inputs, and the
server's `ROUTES` table is asserted against the sitemap by `tools/check_site.py`.
A page cannot be added to the build and forgotten in the sitemap, and the
sitemap cannot advertise a URL that 404s.

**What `tools/check_site.py` enforces**, against the real app and the real
build, on every run:

- every route returns 200, with a title and description, both unique
- canonical URLs are absolute and point at *themselves* — a canonical that
  points elsewhere silently hands your ranking to another page
- exactly one `<h1>` per page and no skipped heading level
- every `<img>` has an `alt` attribute
- JSON-LD parses, and every `FAQPage` question is **visible on that page**
  (Google treats declaring more than you show as a manual action)
- no internal link 404s
- `/app.html` and friends `301` to their clean URLs, so one page is not two
- HTML revalidates and hashed assets are `immutable`
- an unknown page returns a 404 status with a `noindex` HTML body, while an
  unknown *API* path still returns JSON

> The FAQ-visibility check was written wrong the first time and passed a
> deliberately poisoned page: it matched questions against text that still
> contained the JSON-LD block, so a question always "appeared". It is worth
> recording that a check only counts once you have watched it fail.

**Analytics and cookies.** The site sets no cookies, so it shows no cookie
banner — a consent dialog for cookies that do not exist trains people to click
through consent dialogs. `VITE_ANALYTICS_SRC` can enable a cookieless
aggregate counter (Plausible/Umami-compatible) at build time; unset, which is
the default, the pages contain no third-party request at all. Local storage is
used for one thing, the panel sizes, and the privacy policy names the keys.

**Accessibility.** Skip links on every page; the palette checked against WCAG
AA (a separate `--border-control` token exists because the decorative border
sits at 1.34:1, fine for a divider and not fine for the edge of a button);
visible focus rings; icon buttons given real labels rather than a glyph; the
graph and tree SVGs given `role="img"` and a description generated from the
same state they draw; `prefers-reduced-motion` honoured.

**Mobile.** The studio is four panels separated by draggable dividers, and a
phone has no drag-a-divider gesture. Below 900 px it becomes one panel and a
tab bar — same components, same state, different container — rather than a
desktop layout shrunk until it merely fits.
