"""Request/response DTOs.

Deliberately separate from the engine's dataclasses: the wire format is allowed
to change independently of the internal model, and the engine must stay usable
without pydantic (it runs inside the sandbox, where every import counts).
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Granularity = Literal["minimal", "standard", "verbose"]


class RunOptions(BaseModel):
    strict_capabilities: bool = False
    lifters: bool | None = None
    max_seconds: float | None = Field(default=None, gt=0, le=60)
    max_events: int | None = Field(default=None, gt=0, le=1_000_000)
    use_cache: bool | None = None


class CreateExecution(BaseModel):
    source: str = Field(min_length=1)
    language: str = "python"
    granularity: Granularity = "standard"
    inputs: dict[str, Any] = Field(default_factory=dict)
    entry: str | None = None
    stdin: str = ""
    options: RunOptions = Field(default_factory=RunOptions)


class RunAlgorithm(BaseModel):
    inputs: dict[str, Any] = Field(default_factory=dict)
    granularity: Granularity = "standard"
    options: RunOptions = Field(default_factory=RunOptions)


class AnalyzeRequest(BaseModel):
    source: str = Field(min_length=1)
    language: str = "python"


class AskAI(BaseModel):
    step: int = Field(ge=-1)
    mode: str = "explain_line"
    question: str = ""
    focus: dict[str, Any] = Field(default_factory=dict)
    use_cache: bool = True


class GenerateInput(BaseModel):
    kind: str
    size: int | None = Field(default=None, ge=0, le=5000)
    distribution: str | None = None
    shape: str | None = None
    nodes: int | None = Field(default=None, ge=2, le=60)
    seed: int = 7
    params: dict[str, Any] = Field(default_factory=dict)

    def to_kwargs(self) -> dict[str, Any]:
        out: dict[str, Any] = {"seed": self.seed, **self.params}
        for key in ("size", "distribution", "shape", "nodes"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out


class BenchmarkRequest(BaseModel):
    algorithms: list[str] = Field(min_length=1, max_length=6)
    input_spec: dict[str, Any] = Field(default_factory=lambda: {"kind": "array"})
    sizes: list[int] | None = None
    granularity: Granularity = "minimal"
    name: str = ""


class SaveSession(BaseModel):
    execution_id: str
    ui_state: dict[str, Any] = Field(default_factory=dict)
