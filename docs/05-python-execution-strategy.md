# 05 — Python Execution & Tracing Strategy

*(Deliverable K; §14 of the brief)*

This is the highest-risk technical decision in the project. It determines what can be
observed, how much it costs, and how likely the system is to silently lie about a program.

---

## K.1 Candidate approaches

### 1. `sys.settrace` (frame-level tracing)

CPython calls a callback on `call`, `line`, `return`, `exception`. Variable changes are
recovered by diffing `frame.f_locals` between line events. This is how Python Tutor works.

**Gives you:** exact line coverage with zero source modification; correct handling of every
Python construct including ones you have never thought about; exact call/return; exceptions.

**Cannot give you:** anything sub-statement. `arr[mid] < target` produces one line event.
You cannot distinguish a subscript read from a name read, cannot capture the comparison's
operands or result, cannot know which branch a condition took except by observing the next
line number (which is ambiguous with loops and `elif` chains), and cannot see the *value* of
an expression that is not assigned to a name. `x = f(a[i]) + g(b[j])` is opaque.

**Other issues:** ~50–150x slowdown on tight loops (a callback per line, in Python);
`f_locals` diffing is O(|locals|) per line and cannot distinguish "read" at all;
in CPython ≥3.13 (PEP 667) `f_locals` semantics changed to a write-through proxy — reading
still works but the historical snapshot-mutation tricks do not.

*Note:* `sys.monitoring` (PEP 669, 3.12+) is a lower-overhead, event-selective successor,
and adds `BRANCH`, `JUMP`, and `INSTRUCTION` events. It closes part of the branch-visibility
gap but still gives nothing at expression level, and it ties the project to 3.12+ behaviour.

### 2. AST transformation (source-to-source instrumentation)

Rewrite the parsed AST, inserting calls to a probe library, then `compile()` and execute
the result.

**Gives you:** exactly the granularity you design. `arr[mid]` becomes
`_as_sub_get(arr, mid, ln)` — you know it is a subscript read, on which container, at which
index, yielding which value. Conditions become `_as_cond(expr, 'if', ln, "low <= high")` —
you get the source text, the operands, and the boolean result. Loop structure is explicit.
Function entry/exit is explicit. Cost is proportional to *emitted* events, so granularity is
a real dial (RQ5) rather than a filter.

**Costs you:** you must not break semantics. The genuine hazards are evaluation order,
short-circuiting (`and`/`or`, chained comparisons), single-evaluation of augmented-assignment
targets, generator laziness, comprehension scopes, decorators, `global`/`nonlocal`
declarations, walrus in comprehensions, and `lineno` preservation. Each is solvable, but
each is a place where a careless transform produces a program that runs *differently* from
the one the student wrote — the worst possible failure mode for a teaching tool.

### 3. Bytecode instrumentation

Rewrite code objects, injecting probe calls between opcodes.

**Gives you:** expression-level visibility with no source-semantic hazards, and it works on
code you did not parse.

**Costs you:** CPython bytecode is unstable across minor versions (3.11's zero-cost
exceptions and inline caches, 3.12's `sys.monitoring`, 3.13's changes). Correct jump-target
fixup and exception-table rewriting is genuinely hard. Debugging a broken transform means
reading disassembly. This is a multi-month sub-project on its own and version-locks the
whole system.

### 4. Custom interpreter

Write a Python evaluator over the AST/IR.

**Gives you:** total observability and total control; trivially safe (you choose what
exists); trivially deterministic and reversible.

**Costs you:** you are now maintaining a Python implementation. Every real program hits
something you have not implemented — `enumerate` on a `zip`, a default argument evaluated
at def time, `sorted(key=...)`, string formatting, `heapq`. This is the trap that produces
"visualizers" supporting a 40-construct toy language. It also **contradicts the project's
premise**: we claim to visualize the student's own code, and a partial interpreter cannot.

### 5. Debugger protocol (`debugpy`/DAP) driving a real process

**Gives you:** production-grade stepping and true live breakpoints.

**Costs you:** DAP is request/response per step, so building a 10k-event trace means 10k
round trips (seconds to minutes). It also gives *no* sub-expression events, and its variable
inspection is designed for on-demand expansion rather than full-state capture. Wrong tool.

---

## K.2 Comparison

| Criterion | settrace | **AST transform** | bytecode | custom interp | DAP |
|---|---|---|---|---|---|
| Correctness of executed semantics | **perfect** | high (with care) | high | **poor** | perfect |
| Line events | yes | yes | yes | yes | yes |
| Branch taken, with condition value | inferred, ambiguous | **exact** | exact | exact | no |
| Sub-expression values | **no** | **yes** | yes | yes | no |
| Subscript read vs name read | **no** | **yes** | yes | yes | no |
| Container mutation via C methods | no | **yes** (call probes) | yes | yes | no |
| Granularity control | coarse only | **full** | full | full | none |
| Overhead | 50–150x | 3–20x (granularity dependent) | 2–10x | 100x+ | unusable for tracing |
| CPython version stability | good | **excellent** (`ast` is stable) | **poor** | n/a | good |
| Implementation effort | **low** | medium | very high | very high | medium |
| Risk of silently wrong output | low | **medium** (transform bugs) | high | very high | low |
| Supports the project's core claim | no | **yes** | yes | no | no |

---

## K.3 Decision

> **Primary: AST transformation. Fallback: `sys.settrace` shallow mode. Never: bytecode or
> custom interpreter.**

The deciding argument is row *"supports the project's core claim"*. The project's thesis is
that visualization can be **derived** from execution. Derivation requires the event stream
to carry semantics — *this is a comparison, these are its operands, this is the branch
taken, this index of this array was read*. `settrace` cannot produce that information at
any cost, so choosing it would force per-algorithm authored views and collapse the project
back into the thing we said we were not building.

The risk (transform bugs producing wrong behaviour) is real and is managed explicitly:

**Mitigation M1 — differential testing.** Every fixture program is executed twice: once
uninstrumented, once instrumented. `stdout`, return values, and raised exceptions must match
exactly. `tests/test_semantic_preservation.py` runs this over the full fixture corpus plus
generated programs. A transform that changes behaviour fails CI.

**Mitigation M2 — conservative transformation.** For any construct where a
semantics-preserving transform is non-obvious, the transformer **declines to instrument it
finely** and falls back to statement-level probes plus a post-statement frame sync. It emits
`INSTRUMENTATION_SKIPPED` so the UI can say "line 14 is shown at reduced detail" rather than
showing a confident wrong picture.

**Mitigation M3 — shallow mode.** If the transformer raises on a module (a construct it
cannot handle at all), the frontend falls back to a `sys.settrace` recorder producing Tier 0–2
events only. The user gets Python Tutor-grade visualization instead of an error. This is
the graceful degradation §45 requires, and it means *some* visualization is always
available for any parseable Python.

**Mitigation M4 — golden traces.** Reference programs have committed golden event logs.
Unintended changes to instrumentation show up as trace diffs in review.

---

## K.4 The transformation rules

`granularity` gates which rules fire. Rules marked *(std)* are on at `standard`;
*(verb)* only at `verbose`.

### Statements

```python
# every statement in a body gets a preceding line probe
STMT                       ->  _as_line(LINE); STMT
```

Docstrings are left in position 0 (moving them would change `__doc__`), and
`global`/`nonlocal` declarations are hoisted above the inserted probe.

### Assignment

```python
x = EXPR                   ->  x = _as_store('x', EXPR, LINE)
                               # probe reads the caller frame to find the old binding
                               # and to classify scope, then returns EXPR unchanged

a, b = EXPR                ->  a, b = _as_value(EXPR, LINE)
                               _as_sync(('a','b'), LINE)
                               # exact values read back from the frame after binding:
                               # correct for starred/nested targets, no re-evaluation

a[i] = v                   ->  _as_sub_set(v, a, i, LINE)
                               # arg order v,a,i preserves CPython's evaluation order
                               # (value first, then target subexpressions)

o.f = v                    ->  _as_attr_set(v, o, 'f', LINE)

x += EXPR                  ->  x = _as_store('x', _as_inplace('+', _as_load('x',x,LINE),
                                                              EXPR, LINE), LINE)
a[i] += EXPR               ->  _as_sub_aug('+', a, i, EXPR, LINE)   # single evaluation of a,i

del x                      ->  _as_del_name('x', LINE); del x
del a[i]                   ->  _as_sub_del(a, i, LINE)
```

### Control flow

```python
if T: B else: E            ->  if _as_cond(T, 'if', LINE, "src"):
                                   _as_branch('then', LINE); B
                               else:
                                   _as_branch('else', LINE); E

while T: B                 ->  _as_loop_enter(LID,'while',LINE)
                               try:
                                   while _as_cond(T,'while',LINE,"src"):
                                       _as_loop_iter(LID, LINE)
                                       B
                                   else: ORELSE            # preserved
                               finally:
                                   _as_loop_exit(LID, LINE)

for v in IT: B             ->  _as_loop_enter(LID,'for',LINE)
                               try:
                                   for v in _as_iter(LID, IT, LINE):   # generator wrapper
                                       v = _as_store('v', v, LINE)
                                       B
                                   else: ORELSE
                               finally:
                                   _as_loop_exit(LID, LINE)
```

Placing `_as_loop_exit` in `finally` is what makes `break`, `return`-from-loop, and
exceptions all produce a correct `LOOP_FINISHED`. The `_as_iter` wrapper is a generator, so
laziness is preserved — an infinite iterable stays infinite (and is stopped by the budget,
not by materialization).

### Functions

```python
def f(a, b=1, *r, **k):    ->  def f(a, b=1, *r, **k):
    BODY                           _as_enter('f', FID, {'a':a,'b':b,'r':r,'k':k}, LINE)
                                   try:
                                       BODY
                                   finally:
                                       _as_exit(FID)

return EXPR                ->  return _as_return(EXPR, FID, LINE)
```

Decorators, default arguments, and annotations are left untouched (they execute at
definition time in the defining scope; instrumenting them would change binding semantics).

### Expressions

```python
a[i]                       ->  _as_sub_get(a, i, LINE)                    (std)
o.f                        ->  _as_attr_get(o, 'f', LINE)                 (verb)
a OP b                     ->  _as_binop('OP', a, b, LINE)                (verb)
a CMP b                    ->  _as_compare('CMP', a, b, LINE)             (std, single-op only)
a < b < c                  ->  _as_value(a < b < c, LINE)                 (std) — preserves
                               short-circuit by evaluating the whole chain lazily
A and B                    ->  _as_value(A and B, LINE)                   (verb) — lazy
NAME (load)                ->  _as_load('NAME', NAME, LINE)               (verb)
obj.m(args)                ->  _as_method(obj, 'm', LINE, args...)        (std) — snapshots
                               receiver before/after when it is a tracked container
```

The `_as_method` probe is what makes `arr.sort()`, `q.popleft()`, `heapq.heappush(h,x)` and
`s.add(v)` visible. Without it, C-level mutation is a hole in the model.

### Constructs deliberately not finely instrumented (MVP)

Comprehensions, generator expressions, lambdas, `async`/`await`, decorators' own bodies,
`with` bodies (the statement is traced, `__enter__`/`__exit__` are not), `match`. Each
lowers to a line probe plus `_as_sync`, and emits `INSTRUMENTATION_SKIPPED`. Reason:
comprehensions have their own scope in Python 3, so naive probe insertion changes name
resolution; getting this right is V2 work with a real test burden.

---

## K.5 Hybrid detail: what `sys.settrace` is still used for

Even in the primary path, one narrow use remains valuable and cheap: an
`opcode=False, line=False` trace function installed only to observe **exceptions
propagating through frames we did not instrument** (e.g. inside a stdlib call). This gives
accurate `EXCEPTION_RAISED` locations without paying per-line callback cost. It is enabled
only when `policy.trace_exceptions` is true (default on).

Full shallow mode (`settrace` for everything) is a distinct `ShallowPythonFrontend`
implementing the same `LanguageFrontend` interface — proof, incidentally, that the
interface really is implementation-agnostic.

---

## K.6 Overhead expectations (to be measured, not asserted)

The evaluation (§AA) measures overhead as `t_instrumented / t_native` across the fixture
corpus at each granularity. We state a *design target*, not a result:

| Granularity | Target overhead | Target events/sec |
|---|---|---|
| minimal | < 5x | > 200k |
| standard | < 25x | > 100k |
| verbose | < 120x | > 40k |

For the workloads that matter (sorting 200 elements, BFS on 50 nodes, `fib(18)`) even 100x
of a millisecond-scale program is imperceptible. The budget guard, not performance, is what
bounds pathological programs.
