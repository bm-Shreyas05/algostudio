# 06 — Sandbox & Security Design

*(Deliverable L; §15 of the brief)*

---

## L.1 Threat model — stated honestly

Defining who we are defending against is more important than the list of mitigations,
because it determines which mitigations are *sufficient* and which are theatre.

| Adversary | In scope? | Rationale |
|---|---|---|
| **T1. Accidental resource exhaustion** — infinite loops, runaway recursion, `[0]*10**9` | **Yes, primary** | This is what students actually produce, every day. |
| **T2. Curious student** — `import os; os.listdir('/')`, `open('/etc/passwd')`, `requests.get(...)` | **Yes, primary** | Expected in any public deployment. |
| **T3. Opportunistic attacker** — sandbox-escape recipes from the internet, `__subclasses__` gadget chains, fork bombs | **Yes** | Must not succeed with off-the-shelf payloads. |
| **T4. Targeted attacker** — CPython 0-days, kernel LPE, container escape, Spectre-class side channels | **No** | Out of scope for a student project, and we say so rather than implying otherwise. A production deployment would need gVisor/Firecracker and a security review. |

**The single most important statement in this document:** *in-process* restrictions
(builtins denylist, import allowlist) are **defense in depth, not a security boundary**.
CPython is not designed to be sandboxed in-process; `restricted execution` was removed from
the stdlib in Python 2.3 precisely because it could not be made sound. Anyone claiming
`__builtins__`-stripping is a security boundary is wrong. Our boundary is the **OS process
and, in production, the container**. The in-process layer exists to turn accidental and
casual misuse into clear error messages, and to reduce the attack surface reachable before
the real boundary is tested.

---

## L.2 Defense layers

```
┌──────────────────────────────────────────────────────────────────┐
│ L5  Application: per-IP rate limit, concurrent-execution cap,     │
│     max source size, max input size, execution queue              │
├──────────────────────────────────────────────────────────────────┤
│ L4  Container (production): docker run --network none             │
│     --read-only --tmpfs /tmp:size=16m,noexec --memory 256m        │
│     --memory-swap 256m --cpus 0.5 --pids-limit 64                 │
│     --cap-drop ALL --security-opt no-new-privileges               │
│     --user 65534:65534  (+ seccomp profile; gVisor optional)      │
├──────────────────────────────────────────────────────────────────┤
│ L3  OS process: separate process, own process group/job object,   │
│     clean env, cwd = empty temp dir, no inherited handles,        │
│     POSIX: setrlimit(CPU, AS, NOFILE, FSIZE, NPROC), setsid       │
│     Windows: Job Object w/ memory + process-count limits          │
│     wall-clock timeout -> kill whole tree                         │
├──────────────────────────────────────────────────────────────────┤
│ L2  Interpreter: python -I -S -E -B  (isolated, no site, no env,  │
│     no .pyc), curated sys.path, import allowlist meta-finder,     │
│     builtins denylist, stdout/stderr replaced by event proxies    │
├──────────────────────────────────────────────────────────────────┤
│ L1  Instrumentation: execution budget guard inside every probe    │
│     (max events, max steps, max wall time, max recursion depth)   │
└──────────────────────────────────────────────────────────────────┘
```

Layers 1–3 are implemented in the MVP on every platform. Layer 4 ships as a Dockerfile plus
a `DockerSandbox` behind the same interface, used when `ALGOSTUDIO_SANDBOX=docker`. Layer 5
is FastAPI middleware.

### L1 — the budget guard (the halting mechanism)

This is the mitigation that actually solves T1, and it is worth understanding why it is
placed here rather than at the OS level. An infinite loop killed by a 10-second OS timeout
gives the student *nothing*: no events, no partial trace, no explanation. The budget guard
lives inside the probe:

```python
def _tick():
    R.n += 1
    if R.n > R.max_events:
        R.emit(BUDGET_EXCEEDED, {...})
        raise ExecutionBudgetExceeded(...)     # ordinary Python exception
    if (R.n & 0x3FF) == 0 and monotonic() - R.t0 > R.max_seconds:
        ...
```

Because it raises an ordinary exception at a known point, the program unwinds cleanly, the
event file is flushed, and the student gets **the first 200,000 events of their infinite
loop** — which is exactly the material needed to see *why* it never terminates. Turning a
hang into a diagnosable trace is a feature, not just a safety measure.

Defaults: `max_events=200_000`, `max_seconds=10`, `max_recursion=200`, `max_output=1 MiB`,
`max_heap_objects=50_000`. All are per-request overridable downwards, never upwards.

### L2 — interpreter hardening

Child is launched as `python -I -S -E -B child_main.py`.

**Import policy.** A `sys.meta_path` finder consulted before all others:

```
ALLOW: math, random, string, collections, collections.abc, heapq, bisect, itertools,
       functools, operator, typing, dataclasses, enum, fractions, decimal, statistics,
       re, json, copy, array, numbers, abc, algostudio_runtime
DENY (explicit, with a friendly message): os, sys, subprocess, socket, shutil, pathlib,
       importlib, ctypes, threading, multiprocessing, asyncio, http, urllib, requests,
       pickle, marshal, tempfile, glob, io, builtins, gc, inspect, code, codeop, signal
DEFAULT: deny with "module 'X' is not available in AlgoStudio"
```

Allowlist, not denylist, for the default. Denying by default is the only defensible
direction; the explicit DENY list exists purely to produce better error messages for the
modules students actually try.

**Builtins policy.** Removed from the user's `__builtins__`: `open`, `exec`, `eval`,
`compile`, `__import__` (replaced by the policy-checked version), `input` (replaced by a
stdin-feed proxy that emits `STDIN_READ`), `breakpoint`, `help`, `exit`, `quit`,
`globals`, `vars`, `locals`, `memoryview`, `super` is kept, `getattr`/`setattr` kept
(needed by ordinary code; the gadget-chain risk they enable is why L3/L4 exist).

**Attribute policy.** We do **not** attempt to block `__class__`/`__subclasses__`/
`__globals__`. Blocking them reliably is impossible in CPython, and attempting it creates a
false sense of security while breaking legitimate code. Stated as a known limitation.

**Output.** `sys.stdout`/`sys.stderr` are replaced by proxies that emit `STDOUT_WRITE` /
`STDERR_WRITE` events into the same ordered stream. Consequence: program output is
perfectly interleaved with execution events, so the console panel can be scrubbed in time
along with everything else. The real fds carry only harness diagnostics.

### L3 — process isolation (cross-platform)

| Control | POSIX | Windows |
|---|---|---|
| CPU time | `setrlimit(RLIMIT_CPU)` | Job Object `JOB_OBJECT_LIMIT_JOB_TIME` (falls back to wall clock) |
| Address space | `setrlimit(RLIMIT_AS, 256 MiB)` | Job Object `ProcessMemoryLimit` |
| File size | `setrlimit(RLIMIT_FSIZE, 0)` | read-only cwd ACL / no writable path |
| Processes | `setrlimit(RLIMIT_NPROC)` | Job Object `ActiveProcessLimit` |
| Open files | `setrlimit(RLIMIT_NOFILE, 32)` | — |
| Core dumps | `setrlimit(RLIMIT_CORE, 0)` | n/a |
| Group kill | `os.setsid()` + `killpg` | `CREATE_NEW_PROCESS_GROUP` + Job Object terminate |
| Network | (container only) | (container only) |

The MVP runs on Windows for development, so `SubprocessSandbox` degrades explicitly: it
logs which limits are unavailable and records them in `PROGRAM_STARTED.meta.policy_applied`.
**Degradation is recorded, never hidden** — a run that had no memory limit says so.

Environment is scrubbed to a fixed allowlist (`PATH`, `SYSTEMROOT` on Windows,
`PYTHONHASHSEED=0` for reproducibility), so tokens and secrets in the server's environment
are never inherited.

### L4 — container (production)

```dockerfile
FROM python:3.12-slim
RUN useradd -u 65534 -M runner || true
COPY algostudio_runtime /opt/runtime
USER 65534
ENTRYPOINT ["python","-I","-S","-E","-B","/opt/runtime/child_main.py"]
```

```
docker run --rm --network none --read-only
  --tmpfs /tmp:rw,size=16m,noexec,nosuid,nodev
  --memory 256m --memory-swap 256m --cpus 0.5 --pids-limit 64
  --cap-drop ALL --security-opt no-new-privileges
  --user 65534:65534 -v <job>:/job:ro algostudio-runtime
```

Program and inputs are bind-mounted read-only; the event stream is written to a mounted
`/job/out` tmpfs and read after exit (or tailed live via a named pipe on Linux).

**Cost, stated:** container start-up is 150–400 ms, which is a real UX tax on every run. The
mitigation is a **warm pool** of pre-started idle containers (V2); MVP accepts the latency
in Docker mode and uses `SubprocessSandbox` for local development.

---

## L.3 Interface

```python
@dataclass(frozen=True)
class SandboxPolicy:
    max_seconds: float; max_cpu_seconds: float; max_memory_mb: int
    max_events: int; max_output_bytes: int; max_recursion: int
    allowed_modules: frozenset[str]; network: bool = False
    trace_exceptions: bool = True

class Sandbox(Protocol):
    def run(self, job: ExecutionJob, policy: SandboxPolicy) -> SandboxResult: ...

@dataclass
class SandboxResult:
    status: Literal["ok","error","timeout","budget_exceeded","killed","internal_error"]
    events_path: Path
    exit_code: int | None
    wall_ms: float
    peak_rss_mb: float | None
    policy_applied: dict[str, bool]     # which limits were actually installed
    diagnostics: str
```

Everything downstream depends on `SandboxResult`, never on how isolation was achieved. That
is what lets `DockerSandbox` and `SubprocessSandbox` be swapped by configuration and what
would let a future Firecracker or WASM (Pyodide) runner slot in — the latter is an
interesting V3 direction because it moves execution to the client and removes the server
threat surface entirely.

---

## L.4 Adversarial test suite

`tests/test_sandbox_security.py` — each case asserts a *specific* outcome, not merely
"an error occurred":

| # | Payload | Required outcome |
|---|---|---|
| 1 | `while True: pass` | `budget_exceeded`, partial trace present, < 12 s |
| 2 | `def f(): f()` + `f()` | `error` with `RecursionError`, recursion depth capped |
| 3 | `x = [0]*10**9` | `error` or `budget_exceeded`, server RSS unchanged |
| 4 | `import os` | `error`, message names the module, no import performed |
| 5 | `open('/etc/passwd')` | `NameError: open is not defined` |
| 6 | `import socket` / `urllib` | denied at import |
| 7 | `__import__('os')` | denied by the policy-checked `__import__` |
| 8 | `().__class__.__base__.__subclasses__()` | **allowed to run** — asserts we do not pretend to block it; the container is the boundary. Test asserts no file write and no network egress occurred (Docker mode) |
| 9 | `print('x'*10**8)` | truncated at `max_output_bytes`, no OOM |
| 10 | fork bomb via `os` | blocked at import; in Docker mode `--pids-limit` asserted |
| 11 | `while True: L.append(L)` | heap-object cap triggers, cycle encoded as `{"k":"cycle"}` |
| 12 | 50 concurrent infinite loops | all terminated, server responsive, queue depth respected |

Cases 8 and 12 are the ones that keep the project honest: 8 documents a real limitation as
a test, and 12 tests the *system* rather than a single execution.

---

## L.5 Residual risks

| Risk | Severity | Status |
|---|---|---|
| CPython in-process escape via gadget chains | High if no container | **Accepted in dev mode**, mitigated in Docker mode. Deployment docs state Docker mode is mandatory for any multi-user deployment. |
| Container escape (kernel bug) | High | Out of scope (T4). Documented. gVisor recommended for public deployment. |
| CPU side-channel / timing | Low | Out of scope. |
| Windows dev mode has weaker limits | Medium | Recorded in `policy_applied` and shown in the UI; Docker mode available on Windows via WSL2. |
| Event-file disk exhaustion | Medium | `max_output_bytes` + per-execution byte cap + retention job deleting executions older than N days. |
