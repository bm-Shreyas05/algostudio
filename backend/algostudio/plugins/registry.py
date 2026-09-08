"""Plugin discovery and validation.

Discovery is a filesystem scan.  There is deliberately **no central list to
edit** -- that is what makes "adding an algorithm changes zero core files"
(INV-1) true rather than merely intended.  Drop a directory into
``algorithms/`` and it appears in the catalog.

Validation runs the plugin's source through the *same* capability checker as
user code, so a plugin using an unsupported construct is rejected at start-up
with a precise message instead of failing mysteriously at run time.  Plugins are
held to the same support boundary as everyone else, because they are the same
kind of thing.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.errors import AlgorithmNotFoundError
from .base import AlgorithmPlugin

ALGORITHMS_DIR = Path(__file__).resolve().parent.parent / "algorithms"


@dataclass(slots=True)
class ValidationReport:
    plugin_id: str
    ok: bool
    problems: list[str] = field(default_factory=list)
    capability: dict[str, Any] = field(default_factory=dict)


class PluginRegistry:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or ALGORITHMS_DIR
        self._plugins: dict[str, AlgorithmPlugin] = {}
        self._reports: dict[str, ValidationReport] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    def discover(self, force: bool = False) -> dict[str, AlgorithmPlugin]:
        if self._loaded and not force:
            return self._plugins
        self._plugins.clear()
        self._reports.clear()
        if self.directory.exists():
            for plugin_file in sorted(self.directory.glob("*/plugin.py")):
                try:
                    plugin = self._load(plugin_file)
                except Exception as exc:  # pragma: no cover - authoring error
                    self._reports[plugin_file.parent.name] = ValidationReport(
                        plugin_file.parent.name, False, [f"failed to load: {exc}"]
                    )
                    continue
                report = self.validate(plugin)
                self._reports[plugin.id] = report
                if report.ok:
                    self._plugins[plugin.id] = plugin
        self._loaded = True
        return self._plugins

    def _load(self, plugin_file: Path) -> AlgorithmPlugin:
        module_name = f"algostudio_plugin_{plugin_file.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {plugin_file}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        plugin: AlgorithmPlugin = getattr(module, "PLUGIN")
        directory = plugin_file.parent
        plugin.directory = str(directory)
        source_path = directory / "source.py"
        plugin.source = source_path.read_text(encoding="utf-8") if source_path.exists() else ""
        explain_path = directory / "explain.md"
        plugin.explanation = (
            explain_path.read_text(encoding="utf-8") if explain_path.exists() else ""
        )
        return plugin

    def validate(self, plugin: AlgorithmPlugin) -> ValidationReport:
        from ..languages.registry import get as get_frontend

        problems: list[str] = []
        if not plugin.source.strip():
            problems.append("source.py is missing or empty")
            return ValidationReport(plugin.id, False, problems)
        try:
            analysis = get_frontend("python").analyze(plugin.source)
        except Exception as exc:
            return ValidationReport(plugin.id, False, [f"source does not parse: {exc}"])
        capability = analysis.capability.to_dict()
        for issue in analysis.capability.blocking:
            problems.append(
                f"line {issue.line}: {issue.message} ({issue.code})"
            )
        names = {f["name"] for f in analysis.structure["functions"]}
        if plugin.entry not in names:
            problems.append(
                f"entry point {plugin.entry!r} is not defined in source.py "
                f"(found: {', '.join(sorted(names)) or 'none'})"
            )
        params = next(
            (f["params"] for f in analysis.structure["functions"]
             if f["name"] == plugin.entry),
            [],
        )
        declared = [i.name for i in plugin.inputs]
        missing = [p for p in params if p not in declared]
        if missing:
            problems.append(
                f"entry parameters not declared as inputs: {', '.join(missing)}"
            )
        return ValidationReport(plugin.id, not problems, problems, capability)

    # ------------------------------------------------------------------
    def all(self) -> list[AlgorithmPlugin]:
        return list(self.discover().values())

    def get(self, plugin_id: str) -> AlgorithmPlugin:
        plugins = self.discover()
        if plugin_id not in plugins:
            raise AlgorithmNotFoundError(
                f"no algorithm plugin {plugin_id!r}; available: "
                f"{', '.join(sorted(plugins)) or 'none'}"
            )
        return plugins[plugin_id]

    def reports(self) -> dict[str, ValidationReport]:
        self.discover()
        return self._reports


REGISTRY = PluginRegistry()
