# 10 — Data Model, REST API, WebSocket Protocol

*(Deliverables P, Q, R; §30, §31 of the brief)*

---

## P. Database Schema

SQLite for MVP. **Events are not in the database** -- see `01-architecture.md` F.4.

*Implementation note:* the MVP uses stdlib `sqlite3` with a thin DAL rather than
an ORM. The access patterns are a handful of fixed queries, the schema below is
plain portable SQL, and keeping the dependency list short matters more here than
object mapping would buy. Moving to Postgres is a driver swap plus the usual type
adjustments; adopting SQLAlchemy Core at that point is a reasonable call, but it
would be a dependency for its own sake today.

The database holds metadata and pointers; the event log lives on disk.

```sql
CREATE TABLE user (
  id            TEXT PRIMARY KEY,              -- uuid4
  email         TEXT UNIQUE,
  display_name  TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'student',  -- student|instructor|admin
  created_at    TIMESTAMP NOT NULL
);

CREATE TABLE project (
  id          TEXT PRIMARY KEY,
  owner_id    TEXT REFERENCES user(id) ON DELETE CASCADE,
  name        TEXT NOT NULL,
  description TEXT,
  created_at  TIMESTAMP NOT NULL,
  updated_at  TIMESTAMP NOT NULL
);

CREATE TABLE code_file (
  id          TEXT PRIMARY KEY,
  project_id  TEXT REFERENCES project(id) ON DELETE CASCADE,
  path        TEXT NOT NULL,                  -- 'main.py'
  language    TEXT NOT NULL,                  -- 'python'
  content     TEXT NOT NULL,
  content_hash TEXT NOT NULL,                 -- sha256, enables trace reuse
  version     INTEGER NOT NULL DEFAULT 1,
  updated_at  TIMESTAMP NOT NULL,
  UNIQUE(project_id, path, version)
);

CREATE TABLE execution (
  id             TEXT PRIMARY KEY,
  project_id     TEXT REFERENCES project(id) ON DELETE SET NULL,
  code_file_id   TEXT REFERENCES code_file(id) ON DELETE SET NULL,
  algorithm_id   TEXT,                        -- plugin id, NULL for ad-hoc code
  language       TEXT NOT NULL,
  source_hash    TEXT NOT NULL,
  inputs_json    TEXT NOT NULL,               -- bound inputs
  granularity    TEXT NOT NULL,               -- minimal|standard|verbose
  status         TEXT NOT NULL,               -- queued|running|ok|error|timeout|budget_exceeded|killed
  error_json     TEXT,
  event_count    INTEGER NOT NULL DEFAULT 0,
  storage_dir    TEXT NOT NULL,               -- var/executions/<id>
  sandbox_mode   TEXT NOT NULL,               -- subprocess|docker
  policy_json    TEXT NOT NULL,               -- policy requested + policy_applied
  wall_ms        REAL, cpu_ms REAL, peak_rss_mb REAL,
  created_at     TIMESTAMP NOT NULL,
  finished_at    TIMESTAMP
);
CREATE INDEX ix_execution_source ON execution(source_hash, granularity, status);
CREATE INDEX ix_execution_project ON execution(project_id, created_at DESC);

-- Denormalized fold of the event stream. One row per execution.
CREATE TABLE execution_analytics (
  execution_id   TEXT PRIMARY KEY REFERENCES execution(id) ON DELETE CASCADE,
  metrics_json   TEXT NOT NULL,   -- {"statements":812,"comparisons":34,"swaps":11,...}
  line_hits_json TEXT NOT NULL,   -- {"5": 34, "6": 34, ...}
  max_depth      INTEGER NOT NULL,
  peak_heap_objects INTEGER NOT NULL
);

-- Only stored when a step is bookmarked/shared; navigation checkpoints live on disk.
CREATE TABLE execution_bookmark (
  id           TEXT PRIMARY KEY,
  execution_id TEXT REFERENCES execution(id) ON DELETE CASCADE,
  step         INTEGER NOT NULL,
  label        TEXT,
  note         TEXT,
  created_at   TIMESTAMP NOT NULL
);

-- Plugin catalog cache; source of truth remains the filesystem.
CREATE TABLE algorithm (
  id            TEXT PRIMARY KEY,             -- 'dijkstra'
  name          TEXT NOT NULL,
  category      TEXT NOT NULL,
  description   TEXT,
  metadata_json TEXT NOT NULL,                -- full serialized AlgorithmPlugin
  source_hash   TEXT NOT NULL,
  enabled       INTEGER NOT NULL DEFAULT 1,
  discovered_at TIMESTAMP NOT NULL
);

CREATE TABLE benchmark (
  id            TEXT PRIMARY KEY,
  name          TEXT,
  input_spec_json TEXT NOT NULL,              -- {"kind":"array","size":200,"dist":"random","seed":7}
  created_at    TIMESTAMP NOT NULL
);
CREATE TABLE benchmark_run (
  id            TEXT PRIMARY KEY,
  benchmark_id  TEXT REFERENCES benchmark(id) ON DELETE CASCADE,
  algorithm_id  TEXT NOT NULL,
  execution_id  TEXT REFERENCES execution(id) ON DELETE CASCADE,
  metrics_json  TEXT NOT NULL
);

CREATE TABLE ai_query (
  id            TEXT PRIMARY KEY,
  execution_id  TEXT REFERENCES execution(id) ON DELETE CASCADE,
  user_id       TEXT REFERENCES user(id) ON DELETE SET NULL,
  step          INTEGER NOT NULL,
  mode          TEXT NOT NULL,
  question      TEXT NOT NULL,
  answer        TEXT,
  provider      TEXT NOT NULL,                -- anthropic|template|null
  model         TEXT,
  grounding_json TEXT,                        -- GroundingReport
  tokens_in     INTEGER, tokens_out INTEGER, latency_ms REAL,
  created_at    TIMESTAMP NOT NULL
);
CREATE INDEX ix_ai_cache ON ai_query(execution_id, step, mode, question);

CREATE TABLE session (                        -- shareable saved view
  id            TEXT PRIMARY KEY,
  execution_id  TEXT REFERENCES execution(id) ON DELETE CASCADE,
  owner_id      TEXT REFERENCES user(id) ON DELETE SET NULL,
  share_token   TEXT UNIQUE,
  ui_state_json TEXT NOT NULL,                -- step, pinned views, breakpoints, layout
  created_at    TIMESTAMP NOT NULL
);
```

### On-disk layout per execution

```
var/executions/<execution_id>/
├── meta.json           # source, inputs, policy, source_map, capability_report
├── source.py           # exact source executed
├── events.jsonl        # one Event per line, append-only
├── events.idx          # uint64 byte offsets -> O(1) events[i]
├── checkpoints/64.json 128.json ...
└── analytics.json
```

**Trace reuse.** `(source_hash, inputs_hash, granularity, engine_version)` is a cache key.
Re-running identical code returns the stored execution instantly and skips the sandbox
entirely. This makes classroom use (30 students running the same example) cheap and makes
the demo instant.

---

## Q. REST API

Base `\/api\/v1`. JSON. Errors follow RFC 9457 (`application/problem+json`).

### Executions

```http
POST /executions
{
  "language": "python",
  "source": "def bsearch(a,t): ...",
  "inputs": { "a": [1,3,5,7,9], "t": 7 },      // optional named bindings
  "stdin": "",
  "granularity": "standard",                    // minimal|standard|verbose
  "options": { "strict_capabilities": false, "max_seconds": 10, "lifters": true }
}
201 →
{
  "execution_id": "ex_01J…",
  "status": "running",
  "cached": false,
  "capability_report": {
    "supported": true,
    "issues": [ {"line": 14, "severity": "partial",
                 "code": "COMPREHENSION_NOT_INSTRUMENTED",
                 "message": "List comprehension traced at statement level only."} ]
  },
  "ws": "/ws/executions/ex_01J…"
}
422 → problem+json when strict_capabilities and an UNSUPPORTED construct is present.
```

```http
GET /executions/{id}
→ { execution_id, status, language, algorithm_id, event_count, granularity,
    wall_ms, cpu_ms, peak_rss_mb, sandbox_mode, policy_applied,
    error: {type, message, line} | null,
    capability_report, source, source_map, created_at, finished_at }

DELETE /executions/{id}         → 204, removes row and storage_dir
POST   /executions/{id}/cancel  → 202, kills the child if still running
```

### Events

```http
GET /executions/{id}/events?offset=0&limit=2000&types=VARIABLE_WRITTEN,SWAP&frame=3&line=5
→ { "offset":0, "limit":2000, "total":8412, "next_offset":2000, "events":[ Event, ... ] }
```

Filtering is server-side over the indexed file, so the client can pull, e.g., only a
variable's write history for the provenance popover without downloading the stream.

```http
GET /executions/{id}/events/{event_id}      → single Event, fully expanded
GET /executions/{id}/timeline?depth=2       → the collapsed timeline tree (groups, summaries)
```

### State & views

```http
GET /executions/{id}/state?step=1423
→ { step, status, current_loc, frames:[...], globals:{...},
    heap:{ "h7": {...} }, stdout, stderr, exception, annotations, counters }

GET /executions/{id}/state?step=1423&fields=frames,current_loc   # projection
GET /executions/{id}/views?step=1423
→ { "plan":[ {"ref":"h7","view":"array","score":0.94,"reason":"list of 8 numbers",
              "props":{...},"alternatives":[{"view":"table","score":0.30}]} ] }
GET /executions/{id}/analytics
→ { metrics:{statements,comparisons,swaps,array_reads,array_writes,function_calls,
             max_depth,loop_iterations,algorithm_events:{visit:12,relax:31}},
    line_hits:{...}, timing:{wall_ms,cpu_ms}, complexity_fit:{model:"n log n", r2:0.98} }
GET /executions/{id}/source-map
→ { lines:[{line, statements:[{col,end_col,ir_node_id}], loop_id?, func_id?}] }
```

### Analysis, algorithms, inputs

```http
POST /analyze  {language, source}
→ { capability_report, structure:{functions:[...],loops:[...],recursion:[...],
    data_structures:[...]}, patterns:[{name:"binary_search",confidence:0.78,lines:[4,12]}] }

GET  /algorithms                       → [{id,name,category,description,tags,complexity}]
GET  /algorithms/{id}                  → full metadata + source + explain.md
POST /algorithms/{id}/run  {inputs, granularity} → same shape as POST /executions

POST /inputs/generate
{ "kind":"array", "size":100, "distribution":"nearly_sorted", "seed":42,
  "value_range":[0,999] }
→ { "value":[...], "spec":{...} }
# kinds: array | matrix | string | graph | tree | weighted_graph
# distributions: random | sorted | reverse | nearly_sorted | few_unique | all_equal
```

### Benchmarks

```http
POST /benchmarks
{ "algorithms":["merge_sort","bubble_sort"],
  "input_spec":{"kind":"array","size":200,"distribution":"random","seed":7},
  "repeats": 3 }
→ { benchmark_id, runs:[{algorithm_id, execution_id, metrics:{...}}] }
GET /benchmarks/{id}  → comparison table + per-algorithm execution ids for synced replay
```

### AI

```http
POST /executions/{id}/ai
{ "step": 1423, "mode": "why_value", "question": "Why did mid become 4?",
  "focus": {"variable":"mid"} }
→ { "answer": "...", "provider":"anthropic", "model":"claude-sonnet-5",
    "grounding": { "score":1.0, "verified":4, "unverified":0, "contradicted":0,
                   "claims":[{"text":"low = 3","verified":true,"evidence":{"event_id":37}}] },
    "context_summary": { "events_used": 22, "tokens_in": 2104 },
    "cached": false }
```

### Sessions

```http
POST /sessions {execution_id, ui_state}      → {session_id, share_token, url}
GET  /sessions/{token}                       → {execution_id, ui_state}
```

### Cross-cutting

Rate limits: `POST /executions` 10/min/IP, `POST /ai` 20/min/user. `429` with
`Retry-After`. All list endpoints paginate with `offset`/`limit`. `ETag` on immutable
resources (events, state at a step) so the browser caches aggressively — a finished
execution is immutable, which makes this trivially correct.

---

## R. WebSocket Protocol

`WS /ws/executions/{execution_id}` — one connection per open execution. Purpose: **live
delivery of events while the program is still running**. Navigation is client-side and does
not use the socket.

All frames are JSON `{"v":1,"type":...,"seq":n,...}`.

### Server → client

```jsonc
{"v":1,"type":"hello","seq":0,"execution_id":"ex_…","status":"running",
 "event_count":0,"granularity":"standard","source_map_url":"/api/v1/…"}

{"v":1,"type":"events","seq":1,"from":0,"to":512,"events":[ Event, … ]}
// batched: flushed every 50 ms or 512 events, whichever first

{"v":1,"type":"progress","seq":2,"events":4096,"elapsed_ms":83,"budget_used":0.02}

{"v":1,"type":"stdout","seq":3,"text":"…"}          // convenience mirror; also in events

{"v":1,"type":"finished","seq":9,"status":"ok","event_count":8412,
 "analytics_url":"/api/v1/executions/ex_…/analytics","wall_ms":214}

{"v":1,"type":"error","seq":9,"status":"budget_exceeded",
 "error":{"type":"ExecutionBudgetExceeded","message":"…","line":7},
 "partial":true,"event_count":200000}

{"v":1,"type":"capability","seq":4,
 "issues":[{"line":14,"severity":"partial","code":"COMPREHENSION_NOT_INSTRUMENTED"}]}
```

### Client → server

```jsonc
{"v":1,"type":"subscribe","from_event":0}    // resume after reconnect: replay from index
{"v":1,"type":"cancel"}                      // kill the running child
{"v":1,"type":"ping"}
```

### Design notes

- **The socket is a delivery channel, not a control channel.** Step/seek/play are not WS
  messages because the client already holds the events. This keeps the protocol tiny and
  means a dropped socket degrades to "no live updates", never "the debugger is stuck".
- **Reconnection is trivial**: `subscribe {from_event: n}` replays from the indexed file.
  Because events are immutable and densely indexed, there is no session state to recover.
- **Backpressure**: the server batches and, if the client's send buffer exceeds a threshold,
  drops to `progress`-only frames and lets the client fetch the gap over REST at the end.
  Losing intermediate live frames is harmless; the file is the source of truth.
- **V2 (live control)** would add `{"type":"pause"}`/`{"type":"resume"}` requiring a control
  pipe into the sandbox child. Deliberately excluded from MVP — see `03` §I.5.

---

## Q.2 Error taxonomy

| HTTP | `type` | When |
|---|---|---|
| 400 | `invalid-request` | malformed body |
| 404 | `execution-not-found` / `algorithm-not-found` | — |
| 409 | `execution-still-running` | state requested for an unrecorded step |
| 413 | `source-too-large` / `input-too-large` | > 256 KiB source, > 4 MiB inputs |
| 422 | `unsupported-construct` | strict mode + UNSUPPORTED (includes line and code) |
| 422 | `syntax-error` | includes line, col, and the CPython message |
| 429 | `rate-limited` | with `Retry-After` |
| 503 | `sandbox-unavailable` | Docker not reachable in docker mode |
| 500 | `internal` | never leaks a traceback to the client; logged with a correlation id |

Program errors (a `ZeroDivisionError` in user code) are **not** HTTP errors. They are a
successful execution with `status: "error"` and an `EXCEPTION_RAISED` event — because the
failed run is exactly what the student wants to look at.
