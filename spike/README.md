# Pyodide spike harness

Answers one question: does the engine produce the same event stream in a
browser as it does on the server? Findings are written up in
[`docs/21-pyodide-spike.md`](../docs/21-pyodide-spike.md).

```bash
# 1. ground truth from native CPython (pins PYTHONHASHSEED=0 itself)
python backend/tools/make_pyodide_fixtures.py spike

# 2. package the execution path
python - <<'PY'
import pathlib, zipfile
root = pathlib.Path("backend/algostudio")
with zipfile.ZipFile("spike/algostudio.zip", "w", zipfile.ZIP_DEFLATED) as z:
    z.write(root / "__init__.py", "algostudio/__init__.py")
    for pkg in ("core", "languages", "runtime"):
        for p in (root / pkg).rglob("*.py"):
            if "__pycache__" not in p.parts:
                z.write(p, str(p.relative_to(root.parent).as_posix()))
PY

# 3. serve and open
python -m http.server 8200 --directory spike
```

`fixtures.json` and `algostudio.zip` are generated, not tracked.
