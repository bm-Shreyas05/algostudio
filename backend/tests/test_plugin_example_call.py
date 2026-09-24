"""Opening a catalogue algorithm in the editor must give a program that runs.

A plugin's source only *defines* its algorithm; the catalogue's harness calls
it. Before ``example_call`` existed, a visitor who chose "Edit code" and pressed
Run recorded a program that defined a function and stopped. The studio now
appends ``print(<example_call>)``, and this checks, for every plugin, that the
result is a whole program which runs in the in-browser engine and prints the
same answer the catalogue computes.
"""

from __future__ import annotations

import copy
import json

import pytest

import algostudio.browser.engine as engine
from algostudio.plugins.base import _literal
from algostudio.plugins.registry import REGISTRY

PLUGINS = REGISTRY.all()


@pytest.fixture(autouse=True)
def _job_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "_JOB_DIR", tmp_path)


@pytest.mark.parametrize("plugin", PLUGINS, ids=lambda p: p.id)
def test_edited_copy_runs_and_prints_the_catalogue_answer(plugin):
    program = f"{plugin.source.rstrip()}\n\n\nprint({plugin.example_call()})\n"
    out = json.loads(engine.run(program))
    assert out["status"] == "ok", out.get("error")

    # The answer the catalogue's harness gets, computed in plain Python. Deep
    # copied: several algorithms sort their input in place, and the defaults
    # are the plugin's own objects.
    namespace: dict = {}
    exec(compile(plugin.source, plugin.id, "exec"), namespace)
    expected = namespace[plugin.entry](**copy.deepcopy(plugin.bind_inputs(None)))

    printed = "".join(
        e["payload"].get("text", "") for e in out["events"] if e["type"] == "STDOUT_WRITE"
    )
    assert printed.endswith(f"{expected}\n")


def test_literals_are_python_source():
    for value in ([1, [2, 3]], {"a": (1,)}, {1: "x"}, float("inf"), -float("inf"), "q'\"", None):
        assert eval(_literal(value)) == value
