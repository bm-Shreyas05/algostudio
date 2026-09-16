"""The event stream must be a function of the program, not of the run.

Found while spiking the engine into Pyodide: three consecutive runs of the same
program produced three different event streams. ``enc_opaque`` passed ``repr()``
straight through, and ``repr()`` of a function embeds its address --
``<function f at 0x7f3c8a1b2d40>`` -- which changes on every run.

Nothing was *wrong* on screen, which is why it survived: the address is
cosmetic. But it quietly falsified several things the architecture leans on --
that a cached recording is interchangeable with a fresh one, that the
differential harness compares like with like, and that a recording can be
replayed and hashed at all.
"""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest

from algostudio.core.values import enc_opaque

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: Programs that put a function, module or bare object into a variable, which
#: is what reaches the opaque encoder.
OPAQUE_PROGRAMS = {
    "a lambda": "double = lambda x: x * 2\nprint(double(4))\n",
    "a named function as a value": (
        "def f(x):\n    return x + 1\ng = f\nprint(g(1))\n"
    ),
    "a closure": (
        "def outer(n):\n"
        "    def inner(x):\n"
        "        return x + n\n"
        "    return inner\n"
        "add5 = outer(5)\nprint(add5(1))\n"
    ),
    "an instance without __repr__": (
        "class Thing:\n    pass\nt = Thing()\nprint(type(t).__name__)\n"
    ),
}


def run(source: str) -> list[dict]:
    from algostudio.runtime import child_main

    job_dir = Path(tempfile.mkdtemp())
    try:
        (job_dir / "job.json").write_text(json.dumps({
            "language": "python", "source": source, "inputs": {},
            "granularity": "standard", "entry": None, "stdin": "",
            "budget": {"max_events": 20_000, "max_seconds": 10,
                       "max_output_bytes": 1 << 18, "max_recursion": 200,
                       "max_heap_objects": 50_000},
            "allowed_modules": None,
        }), encoding="utf-8")
        child_main.main(["child_main.py", str(job_dir)])
        return [
            json.loads(line)
            for line in (job_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    finally:
        shutil.rmtree(job_dir, ignore_errors=True)


def stable_part(events: list[dict]) -> str:
    """Everything except the two fields that are clock readings by design."""
    cleaned = []
    for event in events:
        event = {k: v for k, v in event.items() if k != "t"}
        payload = event.get("payload")
        if isinstance(payload, dict):
            event["payload"] = {k: v for k, v in payload.items() if k != "duration_ms"}
        cleaned.append(event)
    return json.dumps(cleaned, sort_keys=True)


class TestNoAddressesLeak:
    @pytest.mark.parametrize("label", sorted(OPAQUE_PROGRAMS))
    def test_no_memory_address_in_the_event_stream(self, label):
        blob = json.dumps(run(OPAQUE_PROGRAMS[label]))
        found = re.findall(r"at 0x[0-9a-fA-F]+", blob)
        assert not found, f"{label}: event stream leaks {found[:3]}"

    def test_the_encoder_still_says_what_the_object_is(self):
        """Stripping the address must not strip the information.

        The repr keeps the qualname, so a lambda defined in here reads as
        ``<function TestNoAddressesLeak.test_....<locals>.<lambda>>`` -- long,
        but it is the part that tells a reader *which* function this is, and
        only the address is removed.
        """
        encoded = enc_opaque(lambda x: x)
        assert encoded["t"] == "function"
        assert "<lambda>" in encoded["repr"]
        assert "0x" not in encoded["repr"]

        class Thing:
            pass

        encoded = enc_opaque(Thing())
        assert "Thing" in encoded["repr"]
        assert encoded["t"] == "Thing"
        assert "0x" not in encoded["repr"]

    def test_a_custom_repr_is_left_alone(self):
        class Point:
            def __repr__(self):
                return "Point(1, 2)"

        assert enc_opaque(Point())["repr"] == "Point(1, 2)"


class TestRunsAreReproducible:
    @pytest.mark.parametrize("label", sorted(OPAQUE_PROGRAMS))
    def test_the_same_program_produces_the_same_events(self, label):
        source = OPAQUE_PROGRAMS[label]
        first, second, third = run(source), run(source), run(source)
        assert stable_part(first) == stable_part(second) == stable_part(third), (
            f"{label}: repeated runs of identical source diverged"
        )

    def test_a_real_fixture_is_reproducible(self):
        source = (FIXTURES / "functions" / "higher_order.py").read_text(encoding="utf-8")
        assert stable_part(run(source)) == stable_part(run(source))
