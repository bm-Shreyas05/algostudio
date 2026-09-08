"""The language frontend interface.

This is the seam that makes INV-2 real: a new language implements
``LanguageFrontend`` and emits the shared ``Event`` schema, and *nothing*
downstream -- state, lifters, shapes, analytics, AI, API, frontend -- changes.

A C++ frontend would satisfy this interface with an entirely different
mechanism (libclang source-to-source instrumentation, or a gdb/MI driver); a
JavaScript frontend with a Babel plugin.  What they share is the output, not
the technique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..core.errors import CapabilityReport
from ..core.ir import Program


@dataclass(slots=True)
class SourceMap:
    """Original-source coordinates for the ids the runtime emits.

    Identity-shaped for Python (the transformer preserves line numbers); a real
    mapping for frontends that compile or transpile.
    """

    lines: int
    functions: dict[str, dict[str, Any]] = field(default_factory=dict)
    loops: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"lines": self.lines, "functions": self.functions, "loops": self.loops}


@dataclass(slots=True)
class AnalysisResult:
    language: str
    capability: CapabilityReport
    program: Program
    source_map: SourceMap
    structure: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "capability_report": self.capability.to_dict(),
            "structure": self.structure,
            "source_map": self.source_map.to_dict(),
        }


@dataclass(slots=True)
class InstrumentOptions:
    granularity: str = "standard"
    trace_exceptions: bool = True


@dataclass(slots=True)
class ExecutionJob:
    """Everything the sandbox needs to run one program."""

    language: str
    source: str
    granularity: str = "standard"
    entry: str | None = None
    inputs: dict[str, Any] = field(default_factory=dict)
    stdin: str = ""
    budget: dict[str, Any] = field(default_factory=dict)
    allowed_modules: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "source": self.source,
            "granularity": self.granularity,
            "entry": self.entry,
            "inputs": self.inputs,
            "stdin": self.stdin,
            "budget": self.budget,
            "allowed_modules": self.allowed_modules,
        }


@runtime_checkable
class LanguageFrontend(Protocol):
    language_id: str
    file_extensions: tuple[str, ...]
    display_name: str

    def analyze(self, source: str) -> AnalysisResult:
        """Parse, classify capabilities, and lower to IR.  Must not execute."""

    def child_entrypoint(self) -> list[str]:
        """Command fragment the sandbox uses to launch this language's runner."""
