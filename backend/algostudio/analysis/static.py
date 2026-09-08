"""Pre-execution program description, and advisory pattern hints.

Reads the IR rather than the Python AST, so this stays language-neutral
(docs/04 §J.4) -- a future C++ frontend gets the analysis panel for free.

Pattern detection is explicitly **advisory** and never load-bearing: it biases
the opening AI explanation and nothing else. A wrong guess must cost the user
nothing, so confidences are reported and the UI presents them as guesses.
"""

from __future__ import annotations

import re
from typing import Any

from ..core.ir import Program

#: (name, description, structural signals)
PATTERNS: list[tuple[str, str, list[str]]] = [
    ("binary_search", "halving search over a sorted sequence",
     [r"\bmid\b.*//\s*2", r"while\s+\w+\s*<=\s*\w+", r"\b(lo|low)\b", r"\b(hi|high)\b"]),
    ("bubble_sort", "adjacent swaps in a nested loop",
     [r"for\s+\w+\s+in\s+range", r"\[\w+\s*\+\s*1\]", r",\s*\w+\[\w+\s*\+\s*1\]\s*="]),
    ("merge_sort", "split, recurse, merge",
     [r"//\s*2", r"\[:\s*mid\s*\]", r"\[\s*mid\s*:\]", r"def\s+merge"]),
    ("quick_sort", "partition around a pivot",
     [r"\bpivot\b", r"def\s+partition", r"\[\w+\]\s*,\s*\w+\[\w+\]\s*="]),
    ("bfs", "queue-driven level-order traversal",
     [r"deque|popleft", r"\bvisited\b", r"for\s+\w+\s+in\s+\w+\[\w+\]"]),
    ("dfs", "stack or recursion driven traversal",
     [r"\bvisited\b", r"\.pop\(\)|def\s+dfs", r"for\s+\w+\s+in\s+\w+\[\w+\]"]),
    ("dijkstra", "greedy shortest path with a priority queue",
     [r"heapq|heappush", r"\bdist\b", r"inf", r"\bvisited\b"]),
    ("dynamic_programming", "table filled from smaller subproblems",
     [r"\bdp\b|\bmemo\b|\btable\b", r"for\s+\w+\s+in\s+range", r"\[\w+\s*-\s*1\]"]),
]


def analyze(program: Program, source: str) -> dict[str, Any]:
    structure = program.structure_summary()
    return {
        **structure,
        "counts": {
            "functions": len(program.functions),
            "loops": len(program.loops),
            "conditionals": len(program.root.find("If")),
            "assignments": len(program.root.find("Assign")),
            "returns": len(program.root.find("Return")),
            "try_blocks": len(program.root.find("Try")),
            "classes": len(program.root.find("ClassDef")),
            "comprehensions": len(program.root.find("Comprehension")),
        },
        "patterns": detect_patterns(source),
        "notes": _notes(program),
    }


def detect_patterns(source: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, description, signals in PATTERNS:
        hits = [s for s in signals if re.search(s, source, re.IGNORECASE)]
        if len(hits) < max(2, len(signals) - 1):
            continue
        out.append({
            "name": name,
            "description": description,
            "confidence": round(len(hits) / len(signals), 2),
            "signals_matched": len(hits),
            "signals_total": len(signals),
            "advisory": True,
        })
    out.sort(key=lambda p: p["confidence"], reverse=True)
    return out[:3]


def _notes(program: Program) -> list[str]:
    notes: list[str] = []
    if program.recursive_functions:
        notes.append(
            "Recursive: " + ", ".join(program.recursive_functions)
            + ". The call-tree view will show the recursion."
        )
    if program.max_loop_depth >= 2:
        notes.append(
            f"Loop nesting depth {program.max_loop_depth} -- expect the step "
            f"count to grow faster than linearly with input size."
        )
    structures = sorted(set(program.collections_created))
    if structures:
        notes.append("Builds: " + ", ".join(structures) + ".")
    if program.unsupported:
        notes.append(
            f"{len(program.unsupported)} construct(s) are not modelled; see the "
            f"capability report."
        )
    return notes
