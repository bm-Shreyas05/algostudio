"""Error taxonomy shared by the engine and the API layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    OK = "ok"
    PARTIAL = "partial"        # instrumented at reduced granularity
    DEGRADED = "degraded"      # observed only by post-statement frame sync
    UNSUPPORTED = "unsupported"  # refused or not modelled at all


@dataclass(slots=True)
class CapabilityIssue:
    line: int
    col: int
    severity: Severity
    code: str
    message: str
    construct: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "line": self.line,
            "col": self.col,
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
            "construct": self.construct,
        }


@dataclass(slots=True)
class CapabilityReport:
    issues: list[CapabilityIssue] = field(default_factory=list)

    @property
    def supported(self) -> bool:
        return not any(i.severity is Severity.UNSUPPORTED for i in self.issues)

    @property
    def blocking(self) -> list[CapabilityIssue]:
        return [i for i in self.issues if i.severity is Severity.UNSUPPORTED]

    def add(self, issue: CapabilityIssue) -> None:
        self.issues.append(issue)

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "issues": [i.to_dict() for i in self.issues],
        }


class AlgoStudioError(Exception):
    """Base for all engine errors that map to an API problem type."""

    code = "internal"
    http_status = 500

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_problem(self) -> dict[str, Any]:
        return {
            "type": f"https://algostudio.dev/problems/{self.code}",
            "title": self.code.replace("-", " "),
            "status": self.http_status,
            "detail": self.message,
            **self.details,
        }


class SourceSyntaxError(AlgoStudioError):
    code = "syntax-error"
    http_status = 422


class UnsupportedConstructError(AlgoStudioError):
    code = "unsupported-construct"
    http_status = 422


class InstrumentationError(AlgoStudioError):
    """The transformer could not produce a semantics-preserving rewrite."""

    code = "instrumentation-failed"
    http_status = 422


class SandboxUnavailableError(AlgoStudioError):
    code = "sandbox-unavailable"
    http_status = 503


class ExecutionNotFoundError(AlgoStudioError):
    code = "execution-not-found"
    http_status = 404


class AlgorithmNotFoundError(AlgoStudioError):
    code = "algorithm-not-found"
    http_status = 404


class InputTooLargeError(AlgoStudioError):
    code = "input-too-large"
    http_status = 413


class StepOutOfRangeError(AlgoStudioError):
    code = "step-out-of-range"
    http_status = 409


class ExecutionBudgetExceeded(Exception):
    """Raised *inside the sandbox* when a budget is hit.

    Deliberately a plain exception, and deliberately not derived from
    ``AlgoStudioError``: it must unwind the user's program cleanly so the
    partial trace is flushed and remains navigable.
    """

    def __init__(self, reason: str, limit: Any = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.limit = limit
