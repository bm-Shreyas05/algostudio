"""Package the engine for the browser.

Produces ``frontend/public/engine/algostudio.zip``, which Pyodide unpacks at
runtime. Only the packages the client pipeline actually touches go in: no
``api``, no ``services``, no ``store/db``, no ``sandbox`` -- the browser needs
no sandbox because the tab is the boundary, and shipping one would imply
otherwise.

The bundle is verified before it is written: every module is imported into a
fresh interpreter with *only* the bundle on ``sys.path``, so a missing
dependency fails here rather than as a stack trace in someone's browser.

    python backend/tools/build_browser_bundle.py [output.zip]

The output path is an argument so the Docker build can produce it in a stage
that has Python, and copy it into the stage that has Node.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "algostudio"
OUT = ROOT.parent / "frontend" / "public" / "engine" / "algostudio.zip"

#: The client pipeline: analyse -> execute -> lift -> reduce -> analyse -> views.
INCLUDE = ("core", "languages", "runtime", "lifters", "state", "shapes",
           "analytics", "store", "browser", "ai")

#: Excluded on purpose, and it is worth being explicit about why.
EXCLUDE_NOTE = {
    "api": "HTTP layer; the browser calls the engine directly",
    "services": "composition root for the server, with a database attached",
    "sandbox": "the tab is the boundary; shipping this would imply otherwise",
    "plugins": "bundled algorithms still run on the server",
    "inputs": "generators are a server-side convenience",
    "analysis": "static analysis is only used by the /analyze endpoint",
}

#: store/ is included only for eventlog; db.py would drag in sqlite3.
SKIP_FILES = {"store/db.py", "ai/clients.py"}


def collect() -> list[tuple[Path, str]]:
    files = [(PACKAGE / "__init__.py", "algostudio/__init__.py")]
    for package in INCLUDE:
        for path in sorted((PACKAGE / package).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            arc = path.relative_to(PACKAGE.parent).as_posix()
            if arc.removeprefix("algostudio/") in SKIP_FILES:
                continue
            files.append((path, arc))
    return files


def verify(files: list[tuple[Path, str]]) -> None:
    """Import the whole bundle with nothing else importable."""
    staging = Path(tempfile.mkdtemp())
    try:
        for source, arc in files:
            target = staging / arc
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

        modules = sorted(
            arc.removesuffix(".py").replace("/", ".").removesuffix(".__init__")
            for _, arc in files
        )
        # Prepend the staging copy rather than replacing sys.path -- the
        # stdlib still has to be importable. Isolation is then proved by
        # checking where each module actually came from, which is a stronger
        # test than path manipulation anyway.
        probe = (
            "import sys; sys.path.insert(0, %r)\n"
            "import importlib\n"
            "root = %r\n"
            "for m in %r:\n"
            "    mod = importlib.import_module(m)\n"
            "    origin = getattr(mod, '__file__', '') or ''\n"
            "    assert origin.startswith(root), (m, origin)\n"
            "print('ok', len(%r))\n"
            % (str(staging), str(staging), modules, modules)
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", probe],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            print(result.stdout)
            print(result.stderr, file=sys.stderr)
            raise SystemExit(
                "bundle is not self-contained -- a module it needs was left out"
            )
        print(f"  verified: {result.stdout.strip()} modules import in isolation")
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else OUT
    files = collect()
    verify(files)

    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        for source, arc in files:
            archive.write(source, arc)

    manifest = {
        "modules": len(files),
        "packages": list(INCLUDE),
        "excluded": EXCLUDE_NOTE,
        "bytes": out.stat().st_size,
    }
    (out.parent / "manifest.json").write_text(json.dumps(manifest, indent=2),
                                              encoding="utf-8")
    print(f"  {len(files)} modules, {out.stat().st_size/1024:.0f} KB -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
