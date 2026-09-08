"""Generate the fixture corpus.

Every row of docs/19-capability-matrix.md must have at least one fixture; a row
without one fails the meta-test in tests/unit/test_capability_matrix.py.  The
fixtures are also the input to the differential semantics check, the
time-travel invariants, and the overhead benchmark, so they are written to be
deterministic and short.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "tests" / "fixtures"

FIXTURES: dict[str, str] = {}


def fx(path: str, source: str) -> None:
    FIXTURES[path] = source.strip() + "\n"


# ---------------------------------------------------------------- basics
fx("basics/assignment.py", """
x = 5
y = x + 2
z = y * x
name = "algo"
flag = True
nothing = None
print(x, y, z, name, flag, nothing)
""")

fx("basics/augassign.py", """
n = 10
n += 5
n -= 3
n *= 2
n //= 4
n %= 7
n **= 2
print(n)
xs = [1, 2]
xs += [3]
print(xs)
""")

fx("basics/multi_target.py", """
a = b = c = 7
print(a, b, c)
p, q = 1, 2
p, q = q, p
print(p, q)
head, *rest = [1, 2, 3, 4]
print(head, rest)
(m, (n, o)) = (1, (2, 3))
print(m, n, o)
""")

fx("basics/delete.py", """
d = {"a": 1, "b": 2}
del d["a"]
xs = [1, 2, 3]
del xs[1]
temp = 9
del temp
print(d, xs)
""")

fx("basics/chained_compare.py", """
a, b, c = 1, 5, 9
print(a < b < c)
print(a < b > c)
print(0 <= b <= 10)
print(a != b != c)
""")

fx("basics/slicing.py", """
xs = [0, 1, 2, 3, 4, 5, 6, 7]
print(xs[2:5])
print(xs[:3])
print(xs[5:])
print(xs[::2])
print(xs[::-1])
xs[1:3] = [99, 98]
print(xs)
s = "abcdef"
print(s[1:4], s[::-1])
""")

fx("basics/subscript_ops.py", """
grid = [[0, 0, 0], [0, 0, 0]]
grid[0][1] = 5
grid[1][2] = 7
counts = {}
counts["a"] = 1
counts["a"] += 2
counts["b"] = counts.get("a", 0) * 2
print(grid, counts)
""")

# ---------------------------------------------------------------- control
fx("control/if_elif_else.py", """
def classify(n):
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    elif n < 10:
        return "small"
    else:
        return "large"

for value in [-5, 0, 3, 42]:
    print(value, classify(value))
""")

fx("control/while_loop.py", """
n = 27
steps = 0
while n != 1:
    if n % 2 == 0:
        n = n // 2
    else:
        n = 3 * n + 1
    steps += 1
print("collatz steps", steps)
""")

fx("control/for_range.py", """
total = 0
for i in range(1, 6):
    total += i * i
print(total)
for i in range(3, 0, -1):
    print(i)
""")

fx("control/for_collection.py", """
words = ["alpha", "beta", "gamma"]
for w in words:
    print(w.upper())
scores = {"a": 1, "b": 2}
for key in scores:
    print(key, scores[key])
for i, w in enumerate(words):
    print(i, w)
for a, b in zip([1, 2], [3, 4]):
    print(a + b)
for ch in "xyz":
    print(ch)
""")

fx("control/nested_loops.py", """
pairs = []
for i in range(3):
    for j in range(3):
        if i != j:
            pairs.append((i, j))
print(len(pairs), pairs[:3])
""")

fx("control/break_continue.py", """
found = -1
for i in range(20):
    if i % 7 == 0 and i > 0:
        found = i
        break
    if i % 2 == 0:
        continue
print("found", found)

n = 0
while True:
    n += 1
    if n > 4:
        break
print("n", n)
""")

fx("control/loop_else.py", """
def first_divisor(n):
    for d in range(2, n):
        if n % d == 0:
            return d
    else:
        return None

print(first_divisor(15), first_divisor(13))

i = 0
while i < 3:
    i += 1
else:
    print("while-else ran", i)
""")

# ---------------------------------------------------------------- functions
fx("functions/args.py", """
def describe(a, b=2, *rest, key="k", **extra):
    return (a, b, rest, key, sorted(extra.items()))

print(describe(1))
print(describe(1, 3, 4, 5, key="z", other=9))
""")

fx("functions/closures.py", """
def make_counter(start):
    count = start

    def bump(step):
        nonlocal count
        count += step
        return count

    return bump

c = make_counter(10)
print(c(1), c(2), c(3))

TOTAL = 0

def add_global(n):
    global TOTAL
    TOTAL += n

add_global(5)
add_global(7)
print(TOTAL)
""")

fx("functions/recursion.py", """
def fib(n):
    if n <= 1:
        return n
    return fib(n - 1) + fib(n - 2)

print(fib(7))
""")

fx("functions/mutual_recursion.py", """
def is_even(n):
    if n == 0:
        return True
    return is_odd(n - 1)

def is_odd(n):
    if n == 0:
        return False
    return is_even(n - 1)

print(is_even(6), is_odd(6))
""")

fx("functions/generator.py", """
def countdown(n):
    while n > 0:
        yield n
        n -= 1

total = 0
for v in countdown(4):
    total += v
print(total)
""")

fx("functions/higher_order.py", """
def apply_twice(fn, value):
    return fn(fn(value))

double = lambda v: v * 2
print(apply_twice(double, 3))
print(sorted([3, 1, 2], key=lambda v: -v))
""")

# ---------------------------------------------------------------- data
fx("data/list_ops.py", """
xs = [3, 1, 4, 1, 5]
xs.append(9)
xs.insert(0, 2)
xs.remove(1)
last = xs.pop()
xs.sort()
xs.reverse()
xs.extend([7, 8])
print(xs, last, xs.index(4), xs.count(1))
""")

fx("data/dict_ops.py", """
d = {"a": 1}
d["b"] = 2
d.update({"c": 3})
d.setdefault("d", 4)
value = d.pop("a")
print(sorted(d.items()), value, "b" in d, len(d))
""")

fx("data/set_ops.py", """
s = {1, 2, 3}
s.add(4)
s.discard(1)
t = {3, 4, 5}
print(sorted(s), sorted(s & t), sorted(s | t), sorted(s - t))
""")

fx("data/aliasing.py", """
a = [1, 2, 3]
b = a
b.append(4)
c = a[:]
c.append(5)
print(a, b, c, a is b, a is c)
nested = {"xs": a}
nested["xs"].append(6)
print(a)
""")

fx("data/deque_heapq.py", """
from collections import deque
import heapq

q = deque([1, 2, 3])
q.append(4)
q.appendleft(0)
front = q.popleft()
back = q.pop()
print(list(q), front, back)

h = []
for v in [5, 1, 4, 2]:
    heapq.heappush(h, v)
smallest = heapq.heappop(h)
print(smallest, sorted(h))
""")

fx("data/strings.py", """
s = "Hello, AlgoStudio"
print(s.upper())
print(s.lower().split(", "))
print(s.replace("Hello", "Hi"))
print(f"{len(s)} chars, starts with {s[:5]!r}")
print("-".join(["a", "b", "c"]))
""")

fx("data/nested_structures.py", """
graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
matrix = [[1, 2], [3, 4]]
records = [{"id": 1, "tags": {"x"}}, {"id": 2, "tags": {"y", "z"}}]
matrix[1][0] = 30
graph["A"].append("D")
print(graph, matrix, len(records))
""")

fx("data/cycle.py", """
a = [1, 2]
a.append(a)
node = {"value": 1}
node["self"] = node
print(len(a), node["value"])
""")

# ---------------------------------------------------------------- classes
fx("classes/simple.py", """
class Counter:
    def __init__(self, start=0):
        self.value = start
        self.history = []

    def bump(self, step=1):
        self.value += step
        self.history.append(self.value)
        return self.value

c = Counter(5)
c.bump()
c.bump(3)
print(c.value, c.history)
""")

fx("classes/linked_list.py", """
class Node:
    def __init__(self, value):
        self.value = value
        self.next = None

head = Node(1)
head.next = Node(2)
head.next.next = Node(3)

total = 0
cur = head
while cur is not None:
    total += cur.value
    cur = cur.next
print(total)
""")

fx("classes/tree.py", """
class TreeNode:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None

def insert(root, value):
    if root is None:
        return TreeNode(value)
    if value < root.value:
        root.left = insert(root.left, value)
    else:
        root.right = insert(root.right, value)
    return root

def inorder(node, out):
    if node is None:
        return out
    inorder(node.left, out)
    out.append(node.value)
    inorder(node.right, out)
    return out

root = None
for v in [5, 3, 8, 1, 4]:
    root = insert(root, v)
print(inorder(root, []))
""")

# ---------------------------------------------------------------- errors
fx("errors/zero_division.py", """
def safe_div(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        return None
    finally:
        pass

print(safe_div(10, 2))
print(safe_div(1, 0))
""")

fx("errors/index_error.py", """
xs = [1, 2, 3]
try:
    print(xs[10])
except IndexError as exc:
    print("caught", type(exc).__name__)
try:
    d = {}
    print(d["missing"])
except KeyError:
    print("caught KeyError")
""")

fx("errors/custom_exception.py", """
class ValidationError(Exception):
    pass

def validate(n):
    if n < 0:
        raise ValidationError("negative not allowed")
    return n

for v in [3, -1]:
    try:
        print(validate(v))
    except ValidationError as exc:
        print("error:", exc)
""")

fx("errors/uncaught.py", """
def compute(values):
    total = 0
    for v in values:
        total += 100 // v
    return total

print(compute([5, 2, 0]))
""")

# ---------------------------------------------------------------- algorithms
fx("algorithms/bubble_sort.py", """
def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        swapped = False
        for j in range(n - i - 1):
            if arr[j] > arr[j + 1]:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
                swapped = True
        if not swapped:
            break
    return arr

print(bubble_sort([5, 2, 9, 1, 7, 3]))
""")

fx("algorithms/merge_sort.py", """
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    return merge(left, right)

def merge(left, right):
    out = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            out.append(left[i])
            i += 1
        else:
            out.append(right[j])
            j += 1
    while i < len(left):
        out.append(left[i])
        i += 1
    while j < len(right):
        out.append(right[j])
        j += 1
    return out

print(merge_sort([8, 3, 5, 1, 9, 2]))
""")

fx("algorithms/bfs.py", """
from collections import deque

def bfs(graph, start):
    visited = set()
    order = []
    queue = deque([start])
    visited.add(start)
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in graph[node]:
            if neighbour not in visited:
                visited.add(neighbour)
                queue.append(neighbour)
    return order

graph = {"A": ["B", "C"], "B": ["D"], "C": ["D", "E"], "D": ["E"], "E": []}
print(bfs(graph, "A"))
""")

fx("algorithms/dijkstra.py", """
import heapq

def dijkstra(graph, source):
    dist = {}
    for node in graph:
        dist[node] = float("inf")
    dist[source] = 0
    visited = set()
    heap = [(0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for v, w in graph[u]:
            candidate = d + w
            if candidate < dist[v]:
                dist[v] = candidate
                heapq.heappush(heap, (candidate, v))
    return dist

graph = {
    "A": [("B", 4), ("C", 2)],
    "B": [("D", 5)],
    "C": [("B", 1), ("D", 8)],
    "D": [],
}
print(sorted(dijkstra(graph, "A").items()))
""")

fx("algorithms/kadane.py", """
def max_subarray(arr):
    best = arr[0]
    current = arr[0]
    for i in range(1, len(arr)):
        current = max(arr[i], current + arr[i])
        best = max(best, current)
    return best

print(max_subarray([-2, 1, -3, 4, -1, 2, 1, -5, 4]))
""")

fx("algorithms/quick_sort.py", """
def quick_sort(arr, lo, hi):
    if lo >= hi:
        return
    p = partition(arr, lo, hi)
    quick_sort(arr, lo, p - 1)
    quick_sort(arr, p + 1, hi)

def partition(arr, lo, hi):
    pivot = arr[hi]
    i = lo - 1
    for j in range(lo, hi):
        if arr[j] <= pivot:
            i += 1
            arr[i], arr[j] = arr[j], arr[i]
    arr[i + 1], arr[hi] = arr[hi], arr[i + 1]
    return i + 1

data = [9, 4, 7, 1, 8, 2]
quick_sort(data, 0, len(data) - 1)
print(data)
""")

# ---------------------------------------------------------------- pathological
fx("pathological/infinite_loop.py", """
total = 0
while True:
    total += 1
""")

fx("pathological/deep_recursion.py", """
def descend(n):
    return descend(n + 1)

descend(0)
""")

fx("pathological/big_output.py", """
for i in range(2000):
    print("line", i, "x" * 40)
""")

fx("pathological/wide_list.py", """
xs = list(range(500))
for i in range(len(xs)):
    xs[i] = xs[i] * 2
print(sum(xs))
""")

# ---------------------------------------------------------------- unsupported
fx("unsupported/comprehension.py", """
squares = [n * n for n in range(6)]
evens = {n for n in range(10) if n % 2 == 0}
lookup = {n: n * n for n in range(4)}
gen = (n for n in range(3))
print(squares, sorted(evens), lookup, sum(gen))
""")

fx("unsupported/async_def.py", """
async def fetch(n):
    return n

print("defined")
""")

fx("unsupported/import_os.py", """
import os
print(os.getcwd())
""")

fx("unsupported/file_access.py", """
f = open("secret.txt")
print(f.read())
""")

fx("unsupported/with_statement.py", """
class Ctx:
    def __enter__(self):
        return 42

    def __exit__(self, *args):
        return False

with Ctx() as value:
    print(value)
""")


def main() -> int:
    for rel, source in FIXTURES.items():
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    print(f"wrote {len(FIXTURES)} fixtures to {ROOT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
