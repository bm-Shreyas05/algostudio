"""Checking an answer's factual claims against the recorded execution.

Extraction is deterministic -- regex plus a small grammar over the patterns that
carry checkable facts.  Deliberately not a second LLM: a verifier that can
hallucinate is not a verifier.

The honest caveat, which must be reported alongside any hallucination rate: this
catches only the claims it can parse.  ``verifier_recall`` in the evaluation
protocol measures that, and a contradiction rate without the detector's recall
is not interpretable.  See docs/09 §O.6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..core.values import scalar_of
from ..state.model import ExecutionState

#: Each pattern yields (kind, subject, claimed_value).
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("assignment", re.compile(
        r"\b`?([A-Za-z_]\w*)`?\s*(?:is|=|==|was|becomes|became|holds|equals)\s+"
        r"`?(-?\d+(?:\.\d+)?|True|False|None|'[^']*'|\"[^\"]*\")`?",
    )),
    ("transition", re.compile(
        r"\b`?([A-Za-z_]\w*)`?\s+(?:changed|changes|went|goes)\s+from\s+"
        r"`?(-?\d+(?:\.\d+)?)`?\s+to\s+`?(-?\d+(?:\.\d+)?)`?",
    )),
    ("index", re.compile(
        r"\b`?([A-Za-z_]\w*)\[(-?\d+)\]`?\s*(?:is|=|==|was|equals|holds)\s+"
        r"`?(-?\d+(?:\.\d+)?|'[^']*'|\"[^\"]*\")`?",
    )),
    ("line", re.compile(r"\bline\s+(\d+)\b", re.IGNORECASE)),
    ("count", re.compile(
        r"\b(\d+)\s+(comparisons?|swaps?|visits?|relaxations?|function calls?|"
        r"iterations?|statements?)\b", re.IGNORECASE,
    )),
]

_COUNT_KEYS = {
    "comparison": "comparisons", "comparisons": "comparisons",
    "swap": "swaps", "swaps": "swaps",
    "visit": "visits", "visits": "visits",
    "relaxation": "relaxations", "relaxations": "relaxations",
    "function call": "function_calls", "function calls": "function_calls",
    "iteration": "loop_iterations", "iterations": "loop_iterations",
    "statement": "statements", "statements": "statements",
}


@dataclass(slots=True)
class Claim:
    text: str
    kind: str
    subject: str
    claimed: str
    verified: bool = False
    contradicted: bool = False
    actual: str = ""
    evidence_step: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "kind": self.kind, "subject": self.subject,
            "claimed": self.claimed, "verified": self.verified,
            "contradicted": self.contradicted, "actual": self.actual,
            "evidence_step": self.evidence_step,
        }


@dataclass(slots=True)
class GroundingReport:
    claims: list[Claim] = field(default_factory=list)

    @property
    def verified(self) -> int:
        return sum(1 for c in self.claims if c.verified)

    @property
    def contradicted(self) -> int:
        return sum(1 for c in self.claims if c.contradicted)

    @property
    def unverified(self) -> int:
        return sum(1 for c in self.claims if not c.verified and not c.contradicted)

    @property
    def score(self) -> float:
        return self.verified / len(self.claims) if self.claims else 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 3),
            "verified": self.verified,
            "unverified": self.unverified,
            "contradicted": self.contradicted,
            "claims": [c.to_dict() for c in self.claims],
            "note": (
                "Only claims the verifier can parse are checked; an unverified "
                "claim is not necessarily wrong."
            ),
        }

    def contradiction_summary(self) -> str:
        parts = [
            f"you wrote {c.claimed!r} for {c.subject}, but the trace shows {c.actual!r}"
            for c in self.claims if c.contradicted
        ]
        return "; ".join(parts)


class ClaimVerifier:
    def __init__(self, state: ExecutionState, analytics: dict[str, Any],
                 source_lines: int = 0) -> None:
        self.state = state
        self.analytics = analytics or {}
        self.source_lines = source_lines
        self._bindings = self._collect_bindings()

    def _collect_bindings(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for frame in self.state.frames:
            for name, value in frame.locals.items():
                out[name] = value
        return out

    # ------------------------------------------------------------------
    def verify(self, answer: str) -> GroundingReport:
        report = GroundingReport()
        seen: set[tuple[str, str, str]] = set()
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(answer):
                claim = self._check(kind, match)
                if claim is None:
                    continue
                key = (claim.kind, claim.subject, claim.claimed)
                if key in seen:
                    continue
                seen.add(key)
                report.claims.append(claim)
        return report

    def _check(self, kind: str, match: re.Match[str]) -> Claim | None:
        text = match.group(0)
        if kind == "assignment":
            name, claimed = match.group(1), match.group(2)
            if name not in self._bindings:
                return None
            actual = _fmt(scalar_of(self._bindings[name]), self._bindings[name])
            return _judge(text, kind, name, claimed, actual)
        if kind == "transition":
            name, old, new = match.group(1), match.group(2), match.group(3)
            if name not in self._bindings:
                return None
            actual = _fmt(scalar_of(self._bindings[name]), self._bindings[name])
            return _judge(text, kind, name, new, actual)
        if kind == "index":
            name, index, claimed = match.group(1), int(match.group(2)), match.group(3)
            value = self._element(name, index)
            if value is None:
                return None
            return _judge(text, kind, f"{name}[{index}]", claimed, value)
        if kind == "line":
            line = int(match.group(1))
            if self.source_lines and line > self.source_lines:
                return Claim(text, kind, "line", str(line), False, True,
                             f"the program has only {self.source_lines} lines")
            return None
        if kind == "count":
            claimed, unit = match.group(1), match.group(2).lower()
            key = _COUNT_KEYS.get(unit) or _COUNT_KEYS.get(unit.rstrip("s"))
            metrics = self.analytics.get("metrics", {})
            if not key or key not in metrics:
                return None
            return _judge(text, kind, key, claimed, str(metrics[key]))
        return None

    def _element(self, name: str, index: int) -> str | None:
        value = self._bindings.get(name)
        if not (isinstance(value, dict) and value.get("k") == "ref"):
            return None
        record = self.state.heap.get(value["r"])
        if record is None or "items" not in record:
            return None
        items = record["items"]
        if index < 0:
            index += len(items)
        if not (0 <= index < len(items)):
            return None
        return _fmt(scalar_of(items[index]), items[index])


def _judge(text: str, kind: str, subject: str, claimed: str, actual: str) -> Claim:
    normalized_claim = _normalize(claimed)
    normalized_actual = _normalize(actual)
    if normalized_claim == normalized_actual:
        return Claim(text, kind, subject, claimed, verified=True, actual=actual)
    return Claim(text, kind, subject, claimed, contradicted=True, actual=actual)


def _normalize(value: str) -> str:
    value = value.strip().strip("'\"")
    try:
        number = float(value)
        return str(int(number)) if number == int(number) else str(number)
    except ValueError:
        return value


def _fmt(scalar: Any, encoded: Any) -> str:
    if scalar is not None:
        return str(scalar)
    if isinstance(encoded, dict) and encoded.get("k") == "none":
        return "None"
    if isinstance(encoded, dict) and encoded.get("k") == "ref":
        return f"<{encoded.get('t')}>"
    return str(encoded)
