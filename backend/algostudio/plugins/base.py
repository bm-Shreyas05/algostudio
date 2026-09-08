"""The algorithm plugin contract.

A plugin is **metadata plus an ordinary source file**.  The source is executed
by exactly the same pipeline as code a user types: same transformer, same
sandbox, same probes.  There is no privileged path, and
``tests/integration/test_plugin_source_parity.py`` asserts that running the
packaged source and pasting the same text into the editor produce identical
event streams.

That is not an implementation detail -- it is the proof that this is a platform
rather than an animation library with a code viewer attached.

Note the binding force of each field.  ``viz_hints`` is *advisory*: it adds a
capped bonus to a view the structural detectors already proposed, and can never
select one they did not.  That is what guarantees a student's own Dijkstra gets
the same graph view as the packaged one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

InputKind = Literal[
    "array", "matrix", "graph", "weighted_graph", "tree", "string",
    "int", "float", "node", "bool", "any",
]


@dataclass(slots=True)
class InputField:
    name: str
    kind: InputKind
    default: Any = None
    description: str = ""
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name, "kind": self.kind, "default": self.default,
            "description": self.description, "required": self.required,
        }

    def validate(self, value: Any) -> Any:
        if value is None:
            if self.required and self.default is None:
                raise ValueError(f"input {self.name!r} is required")
            return self.default
        checks = {
            "array": lambda v: isinstance(v, list),
            "matrix": lambda v: isinstance(v, list) and all(isinstance(r, list) for r in v),
            "graph": lambda v: isinstance(v, dict),
            "weighted_graph": lambda v: isinstance(v, dict),
            "tree": lambda v: isinstance(v, (list, dict)),
            "string": lambda v: isinstance(v, str),
            "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
            "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
            "bool": lambda v: isinstance(v, bool),
            "node": lambda v: isinstance(v, (str, int)),
            "any": lambda v: True,
        }
        if not checks[self.kind](value):
            raise ValueError(
                f"input {self.name!r} must be of kind {self.kind}, got "
                f"{type(value).__name__}"
            )
        return value


@dataclass(slots=True)
class Complexity:
    time: str
    space: str
    best: str = ""
    worst: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time, "space": self.space,
            "best": self.best or self.time, "worst": self.worst or self.time,
        }


@dataclass(slots=True)
class VizHint:
    """A *bias*, never a command.  See ViewResolver._hint_bonus."""

    target: str
    view: str
    weight: float = 0.1

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "view": self.view, "weight": self.weight}


@dataclass(slots=True)
class AlgorithmPlugin:
    id: str
    name: str
    category: str
    description: str
    entry: str
    inputs: list[InputField] = field(default_factory=list)
    complexity: Complexity | None = None
    metrics: list[str] = field(default_factory=list)
    viz_hints: list[VizHint] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    annotated: bool = False   # does the source use the algo.* API?

    #: Filled in by the registry at discovery time.
    source: str = ""
    explanation: str = ""
    directory: str = ""

    def bind_inputs(self, provided: dict[str, Any] | None) -> dict[str, Any]:
        provided = provided or {}
        return {f.name: f.validate(provided.get(f.name)) for f in self.inputs}

    def to_dict(self, include_source: bool = False) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id, "name": self.name, "category": self.category,
            "description": self.description, "entry": self.entry,
            "inputs": [i.to_dict() for i in self.inputs],
            "complexity": self.complexity.to_dict() if self.complexity else None,
            "metrics": self.metrics,
            "viz_hints": [h.to_dict() for h in self.viz_hints],
            "invariants": self.invariants,
            "tags": self.tags,
            "annotated": self.annotated,
        }
        if include_source:
            d["source"] = self.source
            d["explanation"] = self.explanation
        return d
