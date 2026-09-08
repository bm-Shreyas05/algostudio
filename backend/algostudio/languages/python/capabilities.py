"""Classify every construct in a program against the support boundary.

The output is the ``CapabilityReport`` returned by ``POST /executions`` and
rendered as gutter markers in the editor.  Its purpose is stated in
docs/19-capability-matrix.md: *the system must always know, and say, what it
does not know.*  Silence about reduced detail is the failure mode an
educational tool cannot afford.
"""

from __future__ import annotations

import ast

from ...core.errors import CapabilityIssue, CapabilityReport, Severity

#: Modules a program may import.  Mirrors runtime/policy.DEFAULT_ALLOWED_MODULES;
#: checked statically so the user is told before the program runs.
ALLOWED_MODULES = frozenset(
    {
        "math", "random", "string", "collections", "heapq", "bisect",
        "itertools", "functools", "operator", "typing", "dataclasses", "enum",
        "fractions", "decimal", "statistics", "re", "json", "copy", "array",
        "numbers", "abc", "types", "time", "datetime",
    }
)

#: Exact module paths allowed in addition to ALLOWED_MODULES.  Only one entry:
#: the no-op ``algo`` shim, so an annotated plugin source stays runnable as
#: plain Python outside AlgoStudio.  Inside the sandbox that import never runs
#: (the guard's `except NameError` branch is dead when `algo` is injected).
ALLOWED_MODULE_PATHS = frozenset({"algostudio.runtime.semantic"})

BLOCKED_NAMES = {
    "eval": "eval is not available",
    "exec": "exec is not available",
    "compile": "compile is not available",
    "open": "file access is not available",
    "__import__": "dynamic import is not available",
    "globals": "globals() is not available",
    "locals": "locals() is not available",
    "vars": "vars() is not available",
    "breakpoint": "breakpoint() is not available",
}

# construct -> (severity, code, message)
PARTIAL_CONSTRUCTS: dict[type, tuple[str, str]] = {
    ast.ListComp: ("COMPREHENSION_NOT_INSTRUMENTED",
                   "List comprehension is traced at statement level only."),
    ast.SetComp: ("COMPREHENSION_NOT_INSTRUMENTED",
                  "Set comprehension is traced at statement level only."),
    ast.DictComp: ("COMPREHENSION_NOT_INSTRUMENTED",
                   "Dict comprehension is traced at statement level only."),
    ast.GeneratorExp: ("COMPREHENSION_NOT_INSTRUMENTED",
                       "Generator expression is traced at statement level only."),
    ast.Lambda: ("LAMBDA_NOT_INSTRUMENTED",
                 "Lambda bodies are not instrumented; the call result is still recorded."),
    ast.With: ("WITH_NOT_INSTRUMENTED",
               "The with body is traced, but __enter__/__exit__ are not."),
    ast.AsyncWith: ("ASYNC_NOT_SUPPORTED", "async with is not supported."),
}


class CapabilityChecker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.report = CapabilityReport()
        self._seen: set[tuple[int, str]] = set()

    def check(self, tree: ast.AST) -> CapabilityReport:
        self.visit(tree)
        return self.report

    # -- helpers ------------------------------------------------------------
    def _add(self, node: ast.AST, severity: Severity, code: str, message: str,
             construct: str = "") -> None:
        line = getattr(node, "lineno", 0)
        key = (line, code)
        if key in self._seen:
            return
        self._seen.add(key)
        self.report.add(
            CapabilityIssue(
                line=line,
                col=getattr(node, "col_offset", 0),
                severity=severity,
                code=code,
                message=message,
                construct=construct or type(node).__name__,
            )
        )

    def _partial(self, node: ast.AST) -> None:
        entry = PARTIAL_CONSTRUCTS.get(type(node))
        if entry:
            code, message = entry
            severity = (
                Severity.UNSUPPORTED if code.startswith("ASYNC") else Severity.PARTIAL
            )
            self._add(node, severity, code, message)

    # -- blocking -----------------------------------------------------------
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._add(
            node, Severity.UNSUPPORTED, "ASYNC_NOT_SUPPORTED",
            "async functions are not modelled by the event engine.",
            "async def",
        )

    def visit_Await(self, node: ast.Await) -> None:
        self._add(node, Severity.UNSUPPORTED, "ASYNC_NOT_SUPPORTED",
                  "await is not modelled by the event engine.", "await")

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._add(node, Severity.UNSUPPORTED, "ASYNC_NOT_SUPPORTED",
                  "async for is not modelled by the event engine.", "async for")
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._check_module(node, alias.name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self._check_module(node, node.module)

    def _check_module(self, node: ast.AST, name: str) -> None:
        root = name.split(".")[0]
        if root in ALLOWED_MODULES or name in ALLOWED_MODULE_PATHS:
            return
        self._add(
            node, Severity.UNSUPPORTED, "MODULE_NOT_AVAILABLE",
            f"Module '{name}' is not available in AlgoStudio. "
            f"Available: {', '.join(sorted(ALLOWED_MODULES))}.",
            f"import {name}",
        )

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in BLOCKED_NAMES:
            self._add(node, Severity.UNSUPPORTED, "BUILTIN_NOT_AVAILABLE",
                      BLOCKED_NAMES[node.id], node.id)

    # -- partial ------------------------------------------------------------
    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._partial(node)
        self.generic_visit(node)

    visit_SetComp = visit_ListComp        # type: ignore[assignment]
    visit_DictComp = visit_ListComp       # type: ignore[assignment]
    visit_GeneratorExp = visit_ListComp   # type: ignore[assignment]

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._partial(node)

    def visit_With(self, node: ast.With) -> None:
        self._partial(node)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._partial(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if _has_yield(node):
            self._add(
                node, Severity.PARTIAL, "GENERATOR_PARTIAL",
                "Generator functions are traced at statement level; frame "
                "enter/exit events are not emitted.",
                "generator function",
            )
        if node.decorator_list:
            self._add(
                node, Severity.PARTIAL, "DECORATOR_PARTIAL",
                "The decorator itself is not instrumented; the decorated body is.",
                "decorator",
            )
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if len(node.bases) > 1:
            self._add(
                node, Severity.DEGRADED, "MULTIPLE_INHERITANCE",
                "Multiple inheritance executes correctly but the MRO is not modelled.",
                "class",
            )
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if any(isinstance(n, ast.Starred) for n in ast.walk(target)):
                self._add(
                    node, Severity.DEGRADED, "STARRED_UNPACKING",
                    "Starred unpacking is recorded by reading values back after "
                    "the statement; per-element detail is not available.",
                    "starred assignment",
                )
        self.generic_visit(node)

    def visit_Match(self, node: ast.AST) -> None:  # pragma: no cover - 3.10+
        self._add(node, Severity.PARTIAL, "MATCH_PARTIAL",
                  "match statements are traced at statement level only.", "match")
        self.generic_visit(node)


def _has_yield(node: ast.AST) -> bool:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return True
        if _has_yield(child):
            return True
    return False


def check(tree: ast.AST) -> CapabilityReport:
    return CapabilityChecker().check(tree)
