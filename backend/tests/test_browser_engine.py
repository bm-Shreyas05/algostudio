"""The browser engine, run the way Pyodide runs it: all in one interpreter.

On the server the user's program runs in a throwaway child process, so
anything it changes about the interpreter dies with it. In the browser there is
no second process -- the program, the engine and the tutor share one Python.
These tests hold the engine to that stricter standard.

They exist because of a leak that standard exposed. child_main installed the
sandbox's import restriction and never removed it. After the first run, the
engine could no longer import its own modules, and the tutor failed on every
question with "'algostudio.ai' is not available in AlgoStudio".
"""

from __future__ import annotations

import json
import sys

import pytest

import algostudio.browser.engine as engine

BUBBLE = (
    "nums = [5, 1, 4, 2]\n"
    "for i in range(len(nums)):\n"
    "    for j in range(len(nums) - 1 - i):\n"
    "        if nums[j] > nums[j + 1]:\n"
    "            nums[j], nums[j + 1] = nums[j + 1], nums[j]\n"
    "print(nums)\n"
)


@pytest.fixture(autouse=True)
def _job_dir(tmp_path, monkeypatch):
    # Pyodide writes to a virtual /algostudio-job; locally use a temp dir.
    monkeypatch.setattr(engine, "_JOB_DIR", tmp_path / "job")


def test_a_run_leaves_the_import_machinery_as_it_found_it():
    before = list(sys.meta_path)
    json.loads(engine.run(BUBBLE))
    assert sys.meta_path == before, "the sandbox import hook outlived the program"


def test_a_program_that_fails_at_runtime_does_not_leak_the_hook_either():
    """The error path, with the restriction actually installed.

    `import os` never gets this far -- static analysis rejects it before
    execution, so the hook is never installed and the test would prove
    nothing. (It rejects `__import__("os")` too.) Any failure *inside* the
    running program exercises the path that matters: the hook is in place, the
    program raises, and only a `finally` removes the hook.
    """
    before = list(sys.meta_path)
    result = json.loads(engine.run("total = 10\nratio = total / 0\n"))
    assert result["status"] == "error", result["status"]
    assert sys.meta_path == before


def test_a_statically_rejected_program_is_reported_not_run():
    before = list(sys.meta_path)
    result = json.loads(engine.run("import os\n"))
    assert result["status"] == "unsupported"
    assert sys.meta_path == before


def test_the_engine_can_still_import_after_running_user_code():
    """The original failure, reproduced directly."""
    json.loads(engine.run(BUBBLE))
    import importlib
    importlib.import_module("algostudio.ai.template")


@pytest.mark.parametrize("mode", ["explain_line", "why_value", "quiz", "explain_algorithm"])
def test_the_tutor_answers_about_a_browser_run(mode):
    run = json.loads(engine.run(BUBBLE))
    answer = json.loads(engine.ask(run["last_step"] // 2, mode, "", "j"))
    assert answer["answer"], f"{mode} returned nothing"
    assert answer["provider"] == "template"
    assert "not available in AlgoStudio" not in answer["answer"]


def test_the_quiz_never_answers_itself():
    run = json.loads(engine.run(BUBBLE))
    for step in range(0, run["last_step"], 7):
        text = json.loads(engine.ask(step, "quiz"))["answer"]
        assert "it is" not in text.lower(), f"step {step}: quiz revealed its answer: {text}"
        assert "just before ``" not in text, f"step {step}: quiz quoted an empty statement"


def test_views_still_resolve_after_asking():
    run = json.loads(engine.run(BUBBLE))
    engine.ask(run["last_step"] // 2, "explain_line")
    plans = json.loads(engine.views(run["last_step"] // 2))
    assert any(p["name"] == "nums" for p in plans)
