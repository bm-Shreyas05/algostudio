"""Deterministic input generators for demos and benchmarking.

Everything is seeded.  A benchmark comparing two algorithms must feed both the
*identical* input, and a study that cannot be re-run is not a study.
"""

from __future__ import annotations

import random
from typing import Any

ARRAY_DISTRIBUTIONS = (
    "random", "sorted", "reverse", "nearly_sorted", "few_unique", "all_equal",
)
GRAPH_SHAPES = ("random", "grid", "tree", "chain", "complete", "dag")


def generate(kind: str, **params: Any) -> dict[str, Any]:
    fn = _GENERATORS.get(kind)
    if fn is None:
        raise ValueError(
            f"unknown input kind {kind!r}; available: {', '.join(sorted(_GENERATORS))}"
        )
    return {"value": fn(**params), "spec": {"kind": kind, **params}}


# ----------------------------------------------------------------------
def array(size: int = 20, distribution: str = "random", seed: int = 7,
          low: int = 0, high: int = 99, **_: Any) -> list[int]:
    if distribution not in ARRAY_DISTRIBUTIONS:
        raise ValueError(f"unknown distribution {distribution!r}")
    rng = random.Random(seed)
    size = max(0, min(size, 5000))
    if distribution == "all_equal":
        return [low] * size
    if distribution == "few_unique":
        pool = [rng.randint(low, high) for _ in range(max(1, size // 8))]
        return [rng.choice(pool) for _ in range(size)]
    values = [rng.randint(low, high) for _ in range(size)]
    if distribution == "sorted":
        values.sort()
    elif distribution == "reverse":
        values.sort(reverse=True)
    elif distribution == "nearly_sorted":
        values.sort()
        for _ in range(max(1, size // 20)):
            i, j = rng.randrange(size or 1), rng.randrange(size or 1)
            values[i], values[j] = values[j], values[i]
    return values


def matrix(rows: int = 4, cols: int = 4, seed: int = 7,
           low: int = 0, high: int = 9, **_: Any) -> list[list[int]]:
    rng = random.Random(seed)
    return [[rng.randint(low, high) for _ in range(cols)] for _ in range(rows)]


def string(length: int = 20, alphabet: str = "abcdefg", seed: int = 7,
           **_: Any) -> str:
    rng = random.Random(seed)
    return "".join(rng.choice(alphabet) for _ in range(length))


def graph(nodes: int = 6, shape: str = "random", density: float = 0.35,
          seed: int = 7, directed: bool = False, **_: Any) -> dict[str, list[str]]:
    rng = random.Random(seed)
    nodes = max(2, min(nodes, 60))
    names = [_node_name(i) for i in range(nodes)]
    adjacency: dict[str, list[str]] = {n: [] for n in names}

    def link(a: str, b: str) -> None:
        if b not in adjacency[a]:
            adjacency[a].append(b)
        if not directed and a not in adjacency[b]:
            adjacency[b].append(a)

    if shape == "chain":
        for i in range(nodes - 1):
            link(names[i], names[i + 1])
    elif shape == "tree":
        for i in range(1, nodes):
            link(names[rng.randrange(i)], names[i])
    elif shape == "complete":
        for i in range(nodes):
            for j in range(i + 1, nodes):
                link(names[i], names[j])
    elif shape == "grid":
        width = max(1, int(nodes ** 0.5))
        for i in range(nodes):
            if i % width and i - 1 >= 0:
                link(names[i - 1], names[i])
            if i - width >= 0:
                link(names[i - width], names[i])
    elif shape == "dag":
        for i in range(nodes):
            for j in range(i + 1, nodes):
                if rng.random() < density:
                    adjacency[names[i]].append(names[j])
    else:
        for i in range(nodes):
            for j in range(i + 1, nodes):
                if rng.random() < density:
                    link(names[i], names[j])
        # Keep it connected: an unreachable component makes a traversal demo
        # look broken when it is behaving correctly.
        for i in range(1, nodes):
            if not adjacency[names[i]]:
                link(names[rng.randrange(i)], names[i])
    return adjacency


def weighted_graph(nodes: int = 6, shape: str = "random", density: float = 0.35,
                   seed: int = 7, min_weight: int = 1, max_weight: int = 9,
                   directed: bool = False, **_: Any) -> dict[str, list[list[Any]]]:
    plain = graph(nodes=nodes, shape=shape, density=density, seed=seed,
                  directed=directed)
    rng = random.Random(seed + 1)
    weights: dict[tuple[str, str], int] = {}
    out: dict[str, list[list[Any]]] = {}
    for source, targets in plain.items():
        out[source] = []
        for target in targets:
            key = tuple(sorted((source, target)))
            if key not in weights:
                weights[key] = rng.randint(min_weight, max_weight)
            out[source].append([target, weights[key]])
    return out


def tree(nodes: int = 7, seed: int = 7, **_: Any) -> dict[str, Any]:
    rng = random.Random(seed)
    values = rng.sample(range(1, 100), min(nodes, 99))

    def insert(node: dict[str, Any] | None, value: int) -> dict[str, Any]:
        if node is None:
            return {"value": value, "left": None, "right": None}
        if value < node["value"]:
            node["left"] = insert(node["left"], value)
        else:
            node["right"] = insert(node["right"], value)
        return node

    root: dict[str, Any] | None = None
    for value in values:
        root = insert(root, value)
    return root or {}


def _node_name(index: int) -> str:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if index < len(letters):
        return letters[index]
    return f"{letters[index // len(letters) - 1]}{letters[index % len(letters)]}"


_GENERATORS = {
    "array": array, "matrix": matrix, "string": string, "graph": graph,
    "weighted_graph": weighted_graph, "tree": tree,
}
