"""The Python language frontend."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

from ...core.errors import SourceSyntaxError
from ..base import AnalysisResult, LanguageFrontend, SourceMap
from . import capabilities, lowering

RUNTIME_ENTRY = Path(__file__).resolve().parents[2] / "runtime" / "child_main.py"


class PythonFrontend:
    """AST-instrumentation frontend.

    ``analyze`` runs in the *server* process (it must, so an unsupported
    construct can be refused before a sandbox is spawned).  The instrumentation
    itself happens inside the child, from the same original source, so the
    compiled code object keeps the user's line numbers -- see
    ``runtime/child_main.py`` for why.
    """

    language_id = "python"
    display_name = "Python 3"
    file_extensions = (".py",)

    def analyze(self, source: str) -> AnalysisResult:
        try:
            tree = ast.parse(source, filename="<algostudio:main>")
        except SyntaxError as exc:
            raise SourceSyntaxError(
                exc.msg or "invalid syntax",
                line=exc.lineno or 0,
                col=exc.offset or 0,
                text=(exc.text or "").rstrip(),
            ) from exc

        report = capabilities.check(tree)
        program = lowering.lower(tree)
        source_map = SourceMap(
            lines=source.count(chr(10)) + 1,
            functions={
                fid: {"name": f.name, "line": f.line, "end_line": f.end_line,
                      "params": f.params, "recursive": f.is_recursive}
                for fid, f in program.functions.items()
            },
            loops={
                lid: {"kind": l.kind, "line": l.line, "end_line": l.end_line,
                      "depth": l.depth, "var": l.var}
                for lid, l in program.loops.items()
            },
        )
        return AnalysisResult(
            language=self.language_id,
            capability=report,
            program=program,
            source_map=source_map,
            structure=program.structure_summary(),
        )

    def child_entrypoint(self) -> list[str]:
        return [sys.executable, "-I", "-B", str(RUNTIME_ENTRY)]

    def default_allowed_modules(self) -> list[str]:
        return sorted(capabilities.ALLOWED_MODULES)


FRONTEND: LanguageFrontend = PythonFrontend()
