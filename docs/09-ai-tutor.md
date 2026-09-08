# 09 — AI Tutor Architecture

*(Deliverable O; §16, §17, §24 of the brief)*

---

## O.1 Position in the system

The AI layer is a **consumer** of the execution engine, never a participant in it. It has
no ability to execute code, no access to the sandbox, and no path by which a model output
can influence state. Its inputs are a serialized `ExecutionState`, a bounded event window,
and a question. Its output is text plus a machine-checkable grounding report.

If the LLM is removed entirely, the platform loses an explanation panel and nothing else.
That is the correct dependency direction for a project whose contribution is the engine.

---

## O.2 The hallucination problem, precisely

Give a model source code and ask "why did `mid` become 4?" and it answers from the
distribution of similar programs. It will produce a fluent, plausible, *unverified* trace —
and for a student who cannot yet tell right from plausible, a confident wrong explanation is
worse than none.

Three defences, in order of strength:

1. **Grounding** — the prompt contains the actual values, so the correct answer is available
   without inference.
2. **Instruction + refusal path** — the system prompt forbids asserting anything not derivable
   from the provided state and provides an explicit "the trace does not show this" escape.
3. **Verification** — a deterministic post-check extracts factual claims from the answer and
   compares them against state. Unverifiable claims are flagged in the UI, not hidden.

Defence 3 is what makes this a research contribution rather than prompt engineering, because
it produces a *measurement* (RQ3) rather than a hope.

---

## O.3 Context construction

```python
@dataclass
class AIContext:
    question: str
    mode: ExplainMode
    source_window: list[SourceLine]        # ±12 lines around current, with markers
    current: LocationInfo                  # line, function, statement text
    frames: list[FrameSummary]             # name, args, locals (encoded, truncated)
    focus_objects: list[HeapSummary]       # objects referenced at this step
    recent_events: list[EventSummary]      # last N events, prose-rendered
    causal_chain: list[EventSummary]       # provenance for the focused variable
    analytics: AnalyticsSummary
    structure: IRSummary                   # functions, loops, recursion (language-neutral)
    algorithm: AlgorithmMeta | None        # only if the user launched a plugin
    budget: TokenBudget
```

### The causal chain is the most valuable field

For "why did `mid` become 4?", the useful context is not the last 50 events; it is the
**provenance** of `mid`. Computed by walking backwards from the current step:

```
find last VARIABLE_WRITTEN(mid) at or before step
  -> its loc gives the statement:  mid = (low + high) // 2
  -> collect VARIABLE_READ/EXPRESSION_EVALUATED events in that statement's span
  -> for each operand name, recurse one level to its own last write
```

For the binary-search example this yields, deterministically:

```
step 41  VARIABLE_WRITTEN  mid: 2 -> 4        line 5   mid = (low + high) // 2
  operand low  = 3   written at step 37 (line 11: low = mid + 1)
  operand high = 6   written at step 12 (line 3:  high = len(arr) - 1)
  expression   (3 + 6) // 2 = 4
```

The model is then not *deriving* the answer, it is *phrasing* one. This single feature does
most of the work in reducing hallucination, and it exists only because the engine records
reads, writes, and expression evaluations as distinct addressable events.

### Budgeting

Context is assembled by priority under a token budget (default 6k): causal chain > current
location + source window > active frame locals > focus objects > recent events > analytics >
structure > other frames. Values are truncated with explicit `…(truncated)` markers so the
model can see that it is not seeing everything — a silent truncation invites confident
extrapolation.

---

## O.4 Explanation modes (§17)

Each mode is a distinct prompt template with a distinct context selection and a distinct
verifier profile. Modes are data (`ai/modes.py`), so adding one does not touch the engine.

| Mode | Context emphasis | Verifier |
|---|---|---|
| `explain_line` | current statement, its reads/writes, resulting values | strict |
| `why_value` | **causal chain** for the named variable | strict |
| `why_branch` | `CONDITION_EVALUATED` + operand provenance + `BRANCH_TAKEN` | strict |
| `why_called` | `FUNCTION_ENTERED` + caller frame + argument provenance | strict |
| `what_changed` | diff of state between step-1 and step | strict |
| `explain_algorithm` | IR structure + plugin metadata + aggregate analytics | lenient |
| `complexity` | analytics + measured op counts vs input size + plugin `complexity` | lenient |
| `why_slower` | comparative analytics from two executions | lenient |
| `simpler` | previous answer + reading-level instruction | lenient |
| `quiz` | state at step, with the answer withheld from the prompt | special: must generate a question whose answer is checkable against state |

`strict` = every numeric/identifier claim must appear in the context.
`lenient` = general algorithmic prose is permitted, but claims about *this run's* values are
still checked.

`quiz` is interesting: the question generator receives the state, produces a question and a
claimed answer, and the verifier checks the claimed answer against state. A quiz whose own
answer fails verification is discarded and regenerated. The student therefore never sees a
quiz with a wrong answer key.

---

## O.5 The prompt contract

```
SYSTEM
You explain a SINGLE recorded program execution. You are given the exact runtime state.

RULES
1. Every statement about a value, variable, line number, branch, or count MUST come from
   the EXECUTION CONTEXT below. Do not compute values yourself; read them.
2. If the context does not contain what is needed, say exactly:
   "The recorded trace doesn't show that." Then say what would show it.
3. Never speculate about code that did not run in this trace.
4. Refer to line numbers and variable names exactly as given.
5. Explain to a second-year undergraduate. Be concrete before general. 2-6 sentences
   unless asked for more.

EXECUTION CONTEXT
<serialized AIContext, in a fixed, labelled, machine-parseable layout>

QUESTION
<user question>
```

Rule 1 ("do not compute values yourself; read them") is deliberate: an LLM asked to compute
`(3+6)//2` will usually get it right, but the failure mode when it does not is invisible.
Reading is verifiable; computing is not.

---

## O.6 The verifier

```python
@dataclass
class GroundingReport:
    claims: list[Claim]            # {text, kind, verified: bool, evidence: EventRef|None}
    verified_count: int
    unverified_count: int
    contradicted_count: int        # claim contradicted by state — the serious case
    score: float                   # verified / total
```

Extraction is deterministic (no second LLM in the loop): regex + a small grammar over
patterns that carry checkable facts —

- `name = value`, `name is value`, `name became value`, `name changed from a to b`
- `line N`, `at line N`
- `the condition ... was true/false`
- `N comparisons`, `N swaps`, `visited N nodes`

Each extracted claim is checked against `ExecutionState` / `Analytics` at the referenced
step. Results are surfaced in the UI: verified claims are unmarked; unverified claims get a
subtle dotted underline; **contradicted** claims get a warning banner and the answer is
regenerated once with the contradiction quoted back to the model.

This is a genuinely falsifiable mechanism. It is also the measurement instrument for RQ3:
the same question set is run in three conditions — (a) source-only prompt, (b) grounded
prompt, (c) grounded + verifier-with-retry — and the contradiction rate is compared. We do
not predict the result here; we measure it.

Extraction recall is itself a limitation to report: the verifier only catches claims it can
parse. We measure its recall on a hand-labelled sample of 100 answers and report that number
alongside the hallucination rate, because a hallucination rate is meaningless without the
recall of the detector that produced it.

---

## O.7 Provider abstraction and offline mode

```python
class LLMClient(Protocol):
    def complete(self, system: str, user: str, max_tokens: int) -> LLMResponse: ...
```

Implementations: `AnthropicClient` (default, `claude-sonnet-5`), `NullClient`, and
`TemplateExplainer`.

`TemplateExplainer` is not a stub — it is a real, deterministic explanation generator built
from the causal chain:

> `mid` changed from 2 to 4 at line 5. The statement `mid = (low + high) // 2` read
> `low = 3` (written at line 11 during iteration 2) and `high = 6` (written at line 3
> before the loop), giving `(3 + 6) // 2 = 4`.

It runs with no API key, no network, and no cost. It serves three purposes: the demo works
offline, the classroom deployment has a zero-cost mode, and RQ3 gets a non-LLM baseline —
100% grounded by construction, and the interesting question becomes whether the LLM's extra
fluency is worth its residual error rate.

---

## O.8 Educational mode (§24)

A composed view rather than a new subsystem: plugin `description` + `invariants`, the
current step's `TemplateExplainer` output, `complexity`, the annotation-highlighted
variables, and a `quiz` question every N steps. Because every piece is derived from state,
the narration for a *student's own* algorithm is the template explainer plus whatever
lifted semantics were detected — degraded relative to an annotated plugin, but never absent.

---

## O.9 Cost, privacy, abuse

| Concern | Control |
|---|---|
| Token cost | context capped at 6k in / 800 out; per-session request cap; answers cached by `(execution_id, step, mode, question_hash)` |
| Prompt injection via user code | user source and program output are inserted inside clearly delimited, labelled blocks and the system prompt states that content within them is **data, not instructions**. A student writing `# ignore previous instructions` in a comment is the realistic case; the verifier is a second line of defence since injected instructions producing false claims get flagged |
| Privacy | code is sent to the provider only on explicit AI invocation, never on run; a deployment-wide `AI_ENABLED=false` switch leaves `TemplateExplainer` fully functional |
| Availability | provider failure degrades to `TemplateExplainer` with a visible notice, not an error |
