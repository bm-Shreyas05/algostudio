"""Building a bounded, typed context from the real execution.

The most valuable thing in here is the **causal chain**.  For "why did `mid`
become 4?", the useful context is not the last fifty events -- it is the
provenance of `mid`: the write that produced it, the reads that fed that write,
and where each of those values came from.  Computing it turns the model's job
from *deriving* an answer into *phrasing* one, which is most of why grounding
reduces confabulation.

That query is only possible because the engine records reads, writes and
expression evaluations as distinct, addressable events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..core.events import Event, EventType, preview, summarize
from ..state.model import ExecutionState
from ..state.timeline import Timeline

SOURCE_WINDOW = 12
RECENT_EVENTS = 18
CHAIN_DEPTH = 2


@dataclass(slots=True)
class ChainLink:
    step: int
    line: int
    description: str
    kind: str
    name: str = ""
    value: str = ""
    depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step, "line": self.line, "description": self.description,
            "kind": self.kind, "name": self.name, "value": self.value,
            "depth": self.depth,
        }


@dataclass(slots=True)
class AIContext:
    question: str
    mode: str
    step: int
    status: str
    current_line: int
    statement: str
    source_window: list[tuple[int, str, bool]] = field(default_factory=list)
    frames: list[dict[str, Any]] = field(default_factory=list)
    focus_objects: list[dict[str, Any]] = field(default_factory=list)
    recent_events: list[dict[str, Any]] = field(default_factory=list)
    causal_chain: list[ChainLink] = field(default_factory=list)
    analytics: dict[str, Any] = field(default_factory=dict)
    structure: dict[str, Any] = field(default_factory=dict)
    algorithm: dict[str, Any] | None = None
    exception: dict[str, Any] | None = None
    stdout_tail: str = ""
    truncated: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question, "mode": self.mode, "step": self.step,
            "status": self.status, "current_line": self.current_line,
            "statement": self.statement,
            "source_window": [
                {"line": n, "text": t, "current": c} for n, t, c in self.source_window
            ],
            "frames": self.frames,
            "focus_objects": self.focus_objects,
            "recent_events": self.recent_events,
            "causal_chain": [c.to_dict() for c in self.causal_chain],
            "analytics": self.analytics,
            "structure": self.structure,
            "algorithm": self.algorithm,
            "exception": self.exception,
            "stdout_tail": self.stdout_tail,
            "truncated": self.truncated,
        }

    def render(self) -> str:
        """The exact text placed in the prompt.

        Labelled, fixed-order, and machine-parseable, so the verifier can later
        check the model's claims against the same material.
        """
        lines: list[str] = []
        add = lines.append
        add(f"STATUS: {self.status}")
        add(f"STEP: {self.step}")
        add(f"CURRENT LINE: {self.current_line}")
        if self.statement:
            add(f"CURRENT STATEMENT: {self.statement}")
        if self.algorithm:
            add(
                f"ALGORITHM: {self.algorithm.get('name')} "
                f"({self.algorithm.get('complexity', {}).get('time', '?')} time)"
            )
        add("")
        add("SOURCE (>> marks the current line):")
        for number, text, current in self.source_window:
            add(f"{'>>' if current else '  '} {number:>4} | {text}")
        add("")
        if self.causal_chain:
            add("CAUSAL CHAIN (how the value in question came to be):")
            for link in self.causal_chain:
                add(f"  {'  ' * link.depth}step {link.step} line {link.line}: {link.description}")
            add("")
        add("CALL STACK (innermost last):")
        for frame in self.frames:
            add(f"  {frame['name']} at line {frame['line']}")
            for name, value in frame["locals"].items():
                add(f"      {name} = {value}")
        add("")
        if self.focus_objects:
            add("OBJECTS REFERENCED AT THIS STEP:")
            for obj in self.focus_objects:
                add(f"  {obj['name'] or obj['ref']} ({obj['kind']}): {obj['preview']}")
            add("")
        if self.recent_events:
            add("RECENT EVENTS (oldest first):")
            for ev in self.recent_events:
                add(f"  step {ev['step']} line {ev['line']}: {ev['description']}")
            add("")
        if self.exception:
            add(f"EXCEPTION: {self.exception['exc_type']}: {self.exception['message']} "
                f"(line {self.exception['line']})")
            add("")
        if self.stdout_tail:
            add("PROGRAM OUTPUT SO FAR:")
            for line in self.stdout_tail.splitlines()[-6:]:
                add(f"  {line}")
            add("")
        if self.analytics:
            add("COUNTS FOR THE WHOLE RUN: " + ", ".join(
                f"{k}={v}" for k, v in sorted(self.analytics.items())
            ))
        if self.structure:
            functions = ", ".join(
                f"{f['name']}({', '.join(f['params'])})"
                + (" [recursive]" if f.get("recursive") else "")
                for f in self.structure.get("functions", [])
            )
            if functions:
                add(f"FUNCTIONS: {functions}")
        if self.truncated:
            # Say so explicitly: a silent truncation invites the model to
            # extrapolate confidently over the part it cannot see.
            add("NOTE: the following were truncated and are incomplete: "
                + ", ".join(self.truncated))
        return "\n".join(lines)


class ContextBuilder:
    def __init__(self, timeline: Timeline, source: str,
                 structure: dict[str, Any] | None = None,
                 algorithm: dict[str, Any] | None = None) -> None:
        self.timeline = timeline
        self.source_lines = source.splitlines()
        self.structure = structure or {}
        self.algorithm = algorithm

    # ------------------------------------------------------------------
    def build(self, step: int, question: str, mode: str,
              focus: dict[str, Any] | None = None,
              analytics: dict[str, Any] | None = None) -> AIContext:
        state = self.timeline.state_at(step)
        focus = focus or {}
        line = state.current_loc.line if state.current_loc else 0
        truncated: list[str] = []

        ctx = AIContext(
            question=question,
            mode=mode,
            step=step,
            status=state.status,
            current_line=line,
            statement=self._line_text(line),
            source_window=self._window(line),
            frames=self._frames(state, truncated),
            focus_objects=self._objects(state, truncated),
            recent_events=self._recent(step),
            causal_chain=self._chain(step, focus.get("variable"), state),
            analytics=(analytics or {}).get("metrics", {}),
            structure=self.structure,
            algorithm=self.algorithm,
            exception=state.exception.to_dict() if state.exception else None,
            stdout_tail=state.stdout[-600:],
            truncated=truncated,
        )
        return ctx

    # ------------------------------------------------------------------
    def _line_text(self, line: int) -> str:
        if 1 <= line <= len(self.source_lines):
            return self.source_lines[line - 1].strip()
        return ""

    def _window(self, line: int) -> list[tuple[int, str, bool]]:
        low = max(1, line - SOURCE_WINDOW // 2)
        high = min(len(self.source_lines), low + SOURCE_WINDOW)
        return [
            (n, self.source_lines[n - 1], n == line) for n in range(low, high + 1)
        ]

    def _frames(self, state: ExecutionState, truncated: list[str]) -> list[dict[str, Any]]:
        out = []
        for frame in state.frames:
            locals_ = {}
            for name, value in list(frame.locals.items())[:24]:
                locals_[name] = _preview_live(value, state, 60)
                if isinstance(value, dict) and value.get("trunc"):
                    truncated.append(name)
            if len(frame.locals) > 24:
                truncated.append(f"{frame.name} locals")
            out.append({"name": frame.name, "line": frame.line, "locals": locals_})
        return out

    def _objects(self, state: ExecutionState, truncated: list[str]) -> list[dict[str, Any]]:
        names = state.ref_names()
        out = []
        seen: set[str] = set()
        for frame in reversed(state.frames):
            for name, value in frame.locals.items():
                if not (isinstance(value, dict) and value.get("k") == "ref"):
                    continue
                ref = value["r"]
                if ref in seen:
                    continue
                seen.add(ref)
                record = state.heap.get(ref)
                if record is None:
                    continue
                if record.get("trunc"):
                    truncated.append(name)
                out.append({
                    "ref": ref,
                    "name": names.get(ref, name),
                    "kind": record.get("t"),
                    "preview": _render_record(record),
                })
                if len(out) >= 8:
                    return out
        return out

    def _recent(self, step: int) -> list[dict[str, Any]]:
        low = max(0, step - RECENT_EVENTS)
        out = []
        for ev in self.timeline.events[low: step + 1]:
            if ev.type in (EventType.LINE_EXECUTED, EventType.VARIABLE_READ):
                continue
            out.append({
                "step": ev.id, "line": ev.line, "description": summarize(ev),
                "origin": ev.origin,
            })
        return out[-RECENT_EVENTS:]

    # ------------------------------------------------------------------
    def _chain(self, step: int, variable: str | None,
               state: ExecutionState, depth: int = 0) -> list[ChainLink]:
        """Walk backwards from a variable to the values that produced it."""
        if not variable or depth > CHAIN_DEPTH:
            return []
        write_index = self.timeline.previous_write(step, variable)
        if write_index is None:
            return []
        write = self.timeline.events[write_index]
        links = [
            ChainLink(
                step=write.id,
                line=write.line,
                description=(
                    f"{variable} {'created as' if write.type is EventType.VARIABLE_CREATED else 'changed to'} "
                    f"{preview(write.payload.get('new') or write.payload.get('value'))}"
                    + (f" (was {preview(write.payload['old'])})"
                       if write.payload.get("old") is not None else "")
                    + f" by: {self._line_text(write.line)}"
                ),
                kind="write",
                name=variable,
                value=preview(write.payload.get("new") or write.payload.get("value")),
                depth=depth,
            )
        ]

        # Operands of the statement that performed the write.  Two sources,
        # because which one is available depends on granularity: recorded read
        # events at `verbose`, and the statement's own identifiers otherwise.
        # Falling back to the source keeps the chain useful at the default
        # granularity, where name reads are deliberately not instrumented.
        operands: list[str] = []
        for ev in self._statement_events(write_index):
            if ev.type is EventType.VARIABLE_READ:
                name = ev.payload.get("name")
                if name and name != variable:
                    operands.append(name)
                    links.append(ChainLink(
                        step=ev.id, line=ev.line,
                        description=f"read {name} = {preview(ev.payload.get('value'))}",
                        kind="read", name=name,
                        value=preview(ev.payload.get("value")), depth=depth + 1,
                    ))
            elif ev.type is EventType.SUBSCRIPT_READ:
                links.append(ChainLink(
                    step=ev.id, line=ev.line,
                    description=(
                        f"read {ev.payload.get('container_name') or ev.payload.get('container_ref')}"
                        f"[{ev.payload.get('index')}] = {preview(ev.payload.get('value'))}"
                    ),
                    kind="read", depth=depth + 1,
                ))
            elif ev.type is EventType.EXPRESSION_EVALUATED:
                links.append(ChainLink(
                    step=ev.id, line=ev.line,
                    description=f"evaluated {summarize(ev)}",
                    kind="expression", depth=depth + 1,
                ))

        if not operands:
            for name in self._identifiers(write.line):
                if name == variable or name not in _visible_names(state):
                    continue
                source_index = self.timeline.previous_write(write_index - 1, name)
                if source_index is None:
                    continue
                source = self.timeline.events[source_index]
                value = source.payload.get("new") or source.payload.get("value")
                links.append(ChainLink(
                    step=source.id, line=source.line,
                    description=(
                        f"{name} = {preview(value)}, written at line "
                        f"{source.line} by: {self._line_text(source.line)}"
                    ),
                    kind="read", name=name, value=preview(value), depth=depth + 1,
                ))
                operands.append(name)

        for name in operands[:3]:
            links.extend(self._chain(write_index - 1, name, state, depth + 1))
        return _dedupe(links) if depth == 0 else links

    def _identifiers(self, line: int) -> list[str]:
        """Names appearing on the right-hand side of the statement at ``line``."""
        text = self._line_text(line)
        if not text:
            return []
        try:
            import ast

            tree = ast.parse(text)
        except SyntaxError:
            return []
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id not in names:
                    names.append(node.id)
        return names

    def _statement_events(self, write_index: int) -> list[Event]:
        """Events belonging to the same statement as the write at ``write_index``."""
        write = self.timeline.events[write_index]
        out: list[Event] = []
        i = write_index - 1
        while i >= 0:
            ev = self.timeline.events[i]
            if ev.type is EventType.LINE_EXECUTED:
                break
            if ev.line != write.line or ev.frame != write.frame:
                break
            out.append(ev)
            i -= 1
        return list(reversed(out))


def _dedupe(links: list[ChainLink]) -> list[ChainLink]:
    """Keep the shallowest mention of each (step, name).

    The two operand sources (recorded reads and statement identifiers) overlap
    with the recursive walk, and a chain that says the same thing three times
    reads as noise -- to a student and to a language model alike.
    """
    seen: set[tuple[int, str]] = set()
    out: list[ChainLink] = []
    for link in links:
        key = (link.step, link.name)
        if key in seen:
            continue
        seen.add(key)
        out.append(link)
    return out


def _preview_live(value: Any, state: ExecutionState, limit: int = 40) -> str:
    """Preview a value, resolving a container's *current* size from the heap.

    The ``n`` on a ref is the length when the encoder first saw the object --
    containers are not re-encoded on every read, which is what keeps a subscript
    read O(1).  Grounding context must show the live size, or the model is being
    told the visited set is empty when it has three members.
    """
    if isinstance(value, dict) and value.get("k") == "ref":
        record = state.heap.get(value["r"])
        if record is not None:
            return f"{record.get('t')} with {record.get('n', 0)} items: " + _render_record(record, 6)
    return preview(value, limit)


def _visible_names(state: ExecutionState) -> set[str]:
    names: set[str] = set()
    for frame in state.frames:
        names.update(frame.locals)
    return names


def _render_record(record: dict[str, Any], limit: int = 10) -> str:
    tag = record.get("t")
    if "items" in record:
        items = [preview(v, 18) for v in record["items"][:limit]]
        more = "" if record.get("n", 0) <= limit else f", ...({record['n']} total)"
        return f"[{', '.join(items)}{more}]"
    if "entries" in record:
        pairs = [
            f"{preview(k, 14)}: {preview(v, 18)}"
            for k, v in record["entries"][:limit]
        ]
        more = "" if record.get("n", 0) <= limit else f", ...({record['n']} total)"
        return "{" + ", ".join(pairs) + more + "}"
    if "fields" in record:
        fields = [f"{k}={preview(v, 18)}" for k, v in list(record["fields"].items())[:limit]]
        return f"{record.get('cls')}({', '.join(fields)})"
    return str(tag)
