"""The visualization-oriented intermediate representation.

Not an execution IR: programs are never run from these nodes (see docs/04-ir.md).
The IR exists so that *static* description of a program -- functions, loops,
recursion, data structures, unsupported constructs -- is expressed in a
language-neutral form that the capability report, the static analysis panel and
the AI context can consume without knowing Python.

``loop_id`` / ``func_id`` / ``call_id`` assigned here are the same ids the
instrumented program emits at runtime, which is what joins static structure to
the event stream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator

from .events import Loc


@dataclass(slots=True)
class Node:
    kind: str
    loc: Loc | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)

    def walk(self) -> Iterator["Node"]:
        yield self
        for c in self.children:
            yield from c.walk()

    def find(self, kind: str) -> list["Node"]:
        return [n for n in self.walk() if n.kind == kind]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"kind": self.kind}
        if self.loc:
            d["loc"] = self.loc.to_dict()
        if self.attrs:
            d["attrs"] = self.attrs
        if self.children:
            d["children"] = [c.to_dict() for c in self.children]
        return d


# Node kinds -- deliberately small.  Statements.
MODULE = "Module"
ASSIGN = "Assign"
AUG_ASSIGN = "AugAssign"
DELETE = "Delete"
EXPR_STMT = "ExprStmt"
IF = "If"
LOOP = "Loop"
FUNC_DEF = "FuncDef"
CLASS_DEF = "ClassDef"
RETURN = "Return"
BREAK = "Break"
CONTINUE = "Continue"
TRY = "Try"
RAISE = "Raise"
IMPORT = "Import"
UNSUPPORTED = "Unsupported"

# Expressions.
CONST = "Const"
NAME = "Name"
BIN_OP = "BinOp"
UNARY_OP = "UnaryOp"
COMPARE = "Compare"
BOOL_OP = "BoolOp"
SUBSCRIPT = "Subscript"
ATTRIBUTE = "Attribute"
CALL = "Call"
MAKE_COLLECTION = "MakeCollection"
COMPREHENSION = "Comprehension"
SLICE = "Slice"
LAMBDA = "Lambda"
IF_EXP = "IfExp"


@dataclass(slots=True)
class FunctionInfo:
    func_id: str
    name: str
    qualname: str
    params: list[str]
    line: int
    end_line: int
    is_recursive: bool = False
    calls: set[str] = field(default_factory=set)


@dataclass(slots=True)
class LoopInfo:
    loop_id: str
    kind: str            # "for" | "while"
    line: int
    end_line: int
    depth: int
    func_id: str | None
    var: str | None = None


@dataclass(slots=True)
class Program:
    """The lowered form of one source module."""

    root: Node
    functions: dict[str, FunctionInfo] = field(default_factory=dict)
    loops: dict[str, LoopInfo] = field(default_factory=dict)
    unsupported: list[Node] = field(default_factory=list)
    collections_created: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)

    @property
    def max_loop_depth(self) -> int:
        return max((l.depth for l in self.loops.values()), default=0)

    @property
    def recursive_functions(self) -> list[str]:
        return [f.name for f in self.functions.values() if f.is_recursive]

    def structure_summary(self) -> dict[str, Any]:
        """Compact, language-neutral description for the UI and the AI context."""
        return {
            "functions": [
                {
                    "id": f.func_id,
                    "name": f.name,
                    "params": f.params,
                    "line": f.line,
                    "recursive": f.is_recursive,
                    "calls": sorted(f.calls),
                }
                for f in self.functions.values()
            ],
            "loops": [
                {
                    "id": l.loop_id,
                    "kind": l.kind,
                    "line": l.line,
                    "depth": l.depth,
                    "var": l.var,
                    "function": l.func_id,
                }
                for l in self.loops.values()
            ],
            "max_loop_depth": self.max_loop_depth,
            "recursive_functions": self.recursive_functions,
            "data_structures": sorted(set(self.collections_created)),
            "imports": sorted(set(self.imports)),
            "unsupported": [
                {
                    "line": n.loc.line if n.loc else 0,
                    "construct": n.attrs.get("original_kind"),
                    "reason": n.attrs.get("reason"),
                }
                for n in self.unsupported
            ],
        }


def compute_recursion(functions: dict[str, FunctionInfo]) -> None:
    """Mark functions that participate in a call cycle (direct or mutual).

    Small Tarjan-free implementation: reachability closure over the call graph,
    which is adequate for programs of the size this system executes.
    """
    by_name: dict[str, FunctionInfo] = {f.name: f for f in functions.values()}
    for fn in functions.values():
        seen: set[str] = set()
        stack = list(fn.calls)
        while stack:
            name = stack.pop()
            if name in seen:
                continue
            seen.add(name)
            if name == fn.name:
                fn.is_recursive = True
                break
            target = by_name.get(name)
            if target is not None:
                stack.extend(target.calls - seen)
