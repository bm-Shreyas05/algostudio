"""The deterministic explainer.

Not a stub.  It generates real explanations from the causal chain and the
recorded state, with no LLM, no API key and no network.

It earns its place three times over:

* the demo works offline, and a classroom deployment has a zero-cost mode;
* provider failure degrades to this rather than to an error;
* it is the **non-LLM baseline** for RQ3 -- 100% grounded by construction, so
  the interesting question becomes whether the LLM's extra fluency is worth its
  residual error rate.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.events import EventType, preview, summarize
from .context import AIContext


def explain(ctx: AIContext) -> str:
    handler = _HANDLERS.get(ctx.mode, _explain_line)
    return handler(ctx)


# ----------------------------------------------------------------------
def _explain_line(ctx: AIContext) -> str:
    if not ctx.statement:
        return f"At step {ctx.step} the program is not on an executable line."
    parts = [f"Line {ctx.current_line} runs `{ctx.statement}`."]
    effects = [
        e["description"] for e in ctx.recent_events
        if e["line"] == ctx.current_line
    ][-4:]
    if effects:
        parts.append("At this step that produced: " + "; ".join(effects) + ".")
    frame = ctx.frames[-1] if ctx.frames else None
    if frame and frame["locals"]:
        shown = ", ".join(f"{k} = {v}" for k, v in list(frame["locals"].items())[:5])
        parts.append(f"In `{frame['name']}` the values are {shown}.")
    return " ".join(parts)


def _why_value(ctx: AIContext) -> str:
    if not ctx.causal_chain:
        return (
            "The recorded trace doesn't show a write to that variable at or "
            "before this step. Step forward to the point where it changes, or "
            "check the spelling of the name."
        )
    root = ctx.causal_chain[0]
    lines = [f"{root.description}"]
    operands = [c for c in ctx.causal_chain[1:] if c.depth == 1]
    if operands:
        lines.append(
            "It was computed from: "
            + "; ".join(c.description for c in operands[:4])
            + "."
        )
    deeper = [c for c in ctx.causal_chain if c.depth >= 2 and c.kind == "write"]
    if deeper:
        lines.append(
            "Those values in turn came from: "
            + "; ".join(f"{c.description}" for c in deeper[:3])
            + "."
        )
    return " ".join(lines)


def _why_branch(ctx: AIContext) -> str:
    condition = next(
        (e for e in reversed(ctx.recent_events) if " -> " in e["description"]
         and e["line"] == ctx.current_line),
        None,
    )
    if condition is None:
        condition = next(
            (e for e in reversed(ctx.recent_events) if " -> " in e["description"]), None
        )
    if condition is None:
        return "The recorded trace doesn't show a condition evaluated at this step."
    branch = next(
        (e for e in reversed(ctx.recent_events)
         if e["description"].startswith("branch:")), None
    )
    text = f"At line {condition['line']}, the condition evaluated as `{condition['description']}`."
    if branch:
        text += f" So the program took the `{branch['description'].split(': ')[-1]}` path."
    frame = ctx.frames[-1] if ctx.frames else None
    if frame and frame["locals"]:
        shown = ", ".join(f"{k} = {v}" for k, v in list(frame["locals"].items())[:4])
        text += f" The values involved at that moment were {shown}."
    return text


def _why_called(ctx: AIContext) -> str:
    call = next(
        (e for e in reversed(ctx.recent_events)
         if e["description"].startswith("call ")), None
    )
    if call is None:
        return "The recorded trace doesn't show a function call at or before this step."
    caller = ctx.frames[-2]["name"] if len(ctx.frames) >= 2 else "<module>"
    return (
        f"At step {call['step']}, line {call['line']} executed `{call['description']}`, "
        f"called from `{caller}`. That pushed a new frame; the call stack is now "
        + " -> ".join(f["name"] for f in ctx.frames) + "."
    )


def _what_changed(ctx: AIContext) -> str:
    changes = [
        e for e in ctx.recent_events
        if any(token in e["description"] for token in ("->", "= ", "swap", "push", "pop"))
    ][-5:]
    if not changes:
        return f"Nothing changed in the state at step {ctx.step}."
    return (
        f"Between the previous step and step {ctx.step}: "
        + "; ".join(e["description"] for e in changes) + "."
    )


def _explain_algorithm(ctx: AIContext) -> str:
    if ctx.algorithm:
        parts = [f"{ctx.algorithm['name']}: {ctx.algorithm['description']}"]
        complexity = ctx.algorithm.get("complexity") or {}
        if complexity:
            parts.append(
                f"Stated complexity: {complexity.get('time')} time, "
                f"{complexity.get('space')} space."
            )
        for invariant in (ctx.algorithm.get("invariants") or [])[:2]:
            parts.append(f"Invariant: {invariant}")
        return " ".join(parts)
    functions = ctx.structure.get("functions", [])
    loops = ctx.structure.get("loops", [])
    recursive = [f["name"] for f in functions if f.get("recursive")]
    depth = ctx.structure.get("max_loop_depth", 0)

    # Written as sentences a person would say. It used to read "defines 0
    # function(s) and 1 loop(s)" -- accurate, and plainly machine output.
    def count(n: int, one: str, many: str) -> str:
        return {0: f"no {many}", 1: f"one {one}"}.get(n, f"{n} {many}")

    names = [f"`{f['name']}`" for f in functions][:4]
    what = count(len(functions), "function", "functions")
    if names:
        what += " (" + ", ".join(names) + ")"
    parts = [f"This program defines {what} and has {count(len(loops), 'loop', 'loops')}."]
    if depth > 1:
        parts.append(
            f"Some loops sit inside others, {depth} deep -- the usual sign that the "
            f"work grows faster than the size of the input."
        )
    if recursive:
        who = ", ".join(f"`{name}`" for name in recursive)
        parts.append(f"{who} {'calls itself' if len(recursive) == 1 else 'call themselves'} (recursion).")
    structures = ctx.structure.get("data_structures") or []
    if structures:
        parts.append("It works with: " + ", ".join(structures) + ".")
    return " ".join(parts)


def _complexity(ctx: AIContext) -> str:
    metrics = ctx.analytics
    stated = ""
    if ctx.algorithm and ctx.algorithm.get("complexity"):
        stated = (
            f" The plugin states {ctx.algorithm['complexity'].get('time')} time "
            f"and {ctx.algorithm['complexity'].get('space')} space."
        )
    measured = ", ".join(
        f"{k} = {v}" for k, v in sorted(metrics.items())
        if k in ("statements", "comparisons", "swaps", "array_reads",
                 "array_writes", "function_calls", "loop_iterations")
    )
    return (
        f"For this input the recorded run performed: {measured}."
        + stated
        + " Run the same algorithm on several input sizes to see how these "
          "counts grow -- the benchmark endpoint fits them against candidate curves."
    )


def _quiz(ctx: AIContext) -> str:
    """A prediction to make, then check by stepping -- never the answer too.

    It used to finish with "(Step forward to check -- it is <value>.)", which
    is a question that answers itself. The value is one glance away in the
    Variables panel for anyone who wants it; the point of asking is to commit
    to a guess first. It also picked the *first* local, which in most programs
    is the whole input list -- "what is arr?" -- so it now prefers a plain
    value: a counter, an index, a flag.
    """
    # Some steps are not on a line of the user's program at all -- between
    # statements, or inside the runtime -- and asking "just before `` runs" on
    # line 657 of a twenty-line program is nonsense. explain_line has always
    # guarded against this; the quiz did not.
    if not ctx.statement:
        return (
            "Predict before you look: which line will run next, and what will "
            "it change? Decide, then step forward to check."
        )
    frame = ctx.frames[-1] if ctx.frames else None
    if frame and frame["locals"]:
        containers = ("list", "dict", "set", "tuple", "deque", "object")
        candidates = list(frame["locals"].items())
        scalar = [
            (name, value) for name, value in candidates
            if not str(value).startswith(containers)
        ]
        # Best of all: a plain value this very line uses. `n` in bubble sort is
        # a scalar too, but it never changes, so predicting it teaches nothing;
        # `j` in `if arr[j] > arr[j + 1]` is the one worth thinking about.
        words = set(re.findall(r"[A-Za-z_]\w*", ctx.statement or ""))
        in_line = [(name, value) for name, value in scalar if name in words]
        name, _value = (in_line or scalar or candidates)[0]
        return (
            f"Predict before you look: at line {ctx.current_line}, just before "
            f"`{ctx.statement}` runs, what is the value of `{name}`? "
            f"Decide on an answer, then check it in the Variables panel."
        )
    return (
        f"Predict before you look: what will line {ctx.current_line} do next? "
        f"Decide, then step forward to check."
    )


def _simpler(ctx: AIContext) -> str:
    return _explain_line(ctx)


_HANDLERS = {
    "explain_line": _explain_line,
    "why_value": _why_value,
    "why_branch": _why_branch,
    "why_called": _why_called,
    "what_changed": _what_changed,
    "explain_algorithm": _explain_algorithm,
    "complexity": _complexity,
    "why_slower": _complexity,
    "simpler": _simpler,
    "quiz": _quiz,
}
