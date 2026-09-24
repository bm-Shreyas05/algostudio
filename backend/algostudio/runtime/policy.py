"""Interpreter-level hardening applied inside the sandbox child.

Read docs/06-sandbox.md before changing anything here.  The important thing to
understand: **this layer is defense in depth, not a security boundary.**  CPython
cannot be sandboxed in-process (this is why ``rexec`` was removed from the
standard library in Python 2.3), and we make no attempt to block gadget chains
such as ``().__class__.__base__.__subclasses__()``.  The real boundary is the OS
process and, in production, the container.

What this layer *does* buy: casual and accidental misuse produces a clear,
teachable error message instead of a filesystem read, and the surface reachable
before the real boundary is exercised is much smaller.
"""

from __future__ import annotations

import builtins
import sys
from types import ModuleType
from typing import Any, Sequence

DEFAULT_ALLOWED_MODULES: frozenset[str] = frozenset(
    {
        "math", "random", "string", "collections", "collections.abc", "heapq",
        "bisect", "itertools", "functools", "operator", "typing", "dataclasses",
        "enum", "fractions", "decimal", "statistics", "re", "json", "copy",
        "array", "numbers", "abc", "types", "time", "datetime",
    }
)

#: Denied explicitly (rather than by default) so the message can be helpful for
#: the modules students actually reach for.
EXPLAIN: dict[str, str] = {
    "os": "filesystem and process access is not available",
    "sys": "interpreter internals are not available",
    "subprocess": "starting processes is not available",
    "socket": "network access is not available",
    "urllib": "network access is not available",
    "urllib.request": "network access is not available",
    "requests": "network access is not available",
    "http": "network access is not available",
    "shutil": "filesystem access is not available",
    "pathlib": "filesystem access is not available",
    "tempfile": "filesystem access is not available",
    "glob": "filesystem access is not available",
    "io": "raw I/O is not available",
    "pickle": "pickle is not available",
    "marshal": "marshal is not available",
    "ctypes": "native code loading is not available",
    "threading": "AlgoStudio models single-threaded execution only",
    "multiprocessing": "AlgoStudio models single-threaded execution only",
    "asyncio": "async execution is not modelled by the event engine",
    "importlib": "dynamic imports are not available",
    "inspect": "interpreter introspection is not available",
    "gc": "the garbage collector is not available",
    "signal": "signals are not available",
    "builtins": "direct builtins access is not available",
}

#: Removed from the user's ``__builtins__``.
BLOCKED_BUILTINS = frozenset(
    {
        "open", "exec", "eval", "compile", "breakpoint", "help", "exit", "quit",
        "input", "__import__", "globals", "vars", "locals", "memoryview",
        "copyright", "credits", "license", "reload",
    }
)


class ImportDenied(ImportError):
    pass


class RestrictedImporter:
    """A ``sys.meta_path`` finder consulted before all others.

    Allowlist by default: an unknown module is denied.  Denying by default is
    the only defensible direction; ``EXPLAIN`` exists purely to give a better
    message for common cases.
    """

    def __init__(self, allowed: Sequence[str]) -> None:
        self.allowed = set(allowed)
        # The only internal path user code may name: the no-op ``algo`` shim
        # that keeps annotated plugin sources runnable outside AlgoStudio.
        self.internal_paths = ("algostudio.runtime.semantic",)

    def find_module(self, fullname: str, path: Any = None) -> None:  # legacy API
        self.check(fullname)
        return None

    def find_spec(self, fullname: str, path: Any = None, target: Any = None) -> None:
        self.check(fullname)
        return None

    def check(self, fullname: str) -> None:
        if fullname in self.internal_paths:
            return
        root = fullname.split(".")[0]
        if fullname in self.allowed or root in self.allowed:
            return
        reason = EXPLAIN.get(fullname) or EXPLAIN.get(root)
        if reason:
            raise ImportDenied(f"'{fullname}' is not available in AlgoStudio: {reason}")
        raise ImportDenied(
            f"'{fullname}' is not available in AlgoStudio. "
            f"Available modules: {', '.join(sorted(self.allowed))}"
        )


def build_safe_builtins(
    extra: dict[str, Any] | None = None,
    stdin_proxy: Any = None,
) -> dict[str, Any]:
    """A copy of ``builtins`` with the dangerous entries removed."""
    safe = {
        name: getattr(builtins, name)
        for name in dir(builtins)
        if name not in BLOCKED_BUILTINS
    }
    safe["__import__"] = _make_checked_import()
    if stdin_proxy is not None:
        safe["input"] = _make_input(stdin_proxy)
    if extra:
        safe.update(extra)
    return safe


def _make_checked_import() -> Any:
    real_import = builtins.__import__

    def checked_import(name: str, globals_: Any = None, locals_: Any = None,
                       fromlist: Any = (), level: int = 0) -> ModuleType:
        for finder in sys.meta_path:
            if isinstance(finder, RestrictedImporter):
                finder.check(name)
                for sub in fromlist or ():
                    if isinstance(sub, str) and sub[:1].islower():
                        try:
                            finder.check(f"{name}.{sub}")
                        except ImportDenied:
                            pass  # attribute access, not a submodule
        return real_import(name, globals_, locals_, fromlist, level)

    return checked_import


def _make_input(stdin_proxy: Any) -> Any:
    def _input(prompt: str = "") -> str:
        if prompt:
            print(prompt, end="")
        line = stdin_proxy.readline()
        return line.rstrip("\n")

    return _input


def install(allowed_modules: Sequence[str] | None = None) -> RestrictedImporter:
    """Install the import restriction.  Returns the finder for later removal."""
    importer = RestrictedImporter(allowed_modules or DEFAULT_ALLOWED_MODULES)
    sys.meta_path.insert(0, importer)
    return importer


def uninstall(importer: RestrictedImporter) -> None:
    """Remove a restriction installed by ``install``.

    For years of this module's life nothing called this, and on the server
    nothing needed to: the sandbox child is a throwaway process, so the hook
    died with it. In the browser the user's program and the engine share one
    interpreter. The hook outlived the program it was guarding and then
    refused the engine's own imports -- the tutor failed with
    "'algostudio.ai' is not available" after the first run of anything.
    """
    try:
        sys.meta_path.remove(importer)
    except ValueError:
        pass
