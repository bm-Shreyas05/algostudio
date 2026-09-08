# 17 — Synopsis Structure, Presentation Structure, Demo Scenarios

*(Deliverables AE, AF, AG; §34 of the brief)*

---

## AE. Final-Year Project Synopsis / Report Structure

Target 70–90 pages. Page budgets are given because the most common failure is 40 pages of
literature survey and 6 pages of design.

| Ch | Title | Pages | Must contain |
|---|---|---|---|
| — | Title, certificate, declaration, acknowledgements | 5 | — |
| — | **Abstract** (250 words) | 1 | problem, approach, what was built, what was measured, one honest limitation |
| — | Contents, list of figures/tables, abbreviations | 4 | — |
| 1 | **Introduction** | 6 | 1.1 background · 1.2 problem statement (from `00-C`) · 1.3 motivation (D1–D5) · 1.4 objectives (O1–O19) · 1.5 scope **and explicit non-scope** · 1.6 contributions (4 bullets, conservative) · 1.7 report organization |
| 2 | **Literature Survey** | 14 | the 12 topics of `15-AD`; ≥ 45 refs; **ends with a gap table** mapping each gap to an objective. Not a list of paper summaries — organized by question |
| 3 | **System Analysis** | 8 | 3.1 existing systems (the honest matrix from `16`) · 3.2 limitations of existing systems · 3.3 proposed system · 3.4 feasibility (technical/economic/operational) · 3.5 functional + non-functional requirements · 3.6 hardware/software requirements |
| 4 | **System Design** | 20 | 4.1 architecture · 4.2 **event model** (the core contribution — give it 5 pages) · 4.3 state model & time travel with the four-option trade-off table · 4.4 IR · 4.5 execution strategy with the five-option comparison · 4.6 sandbox & threat model · 4.7 plugin architecture · 4.8 visualization resolution · 4.9 AI grounding · 4.10 database · 4.11 API/WS · UML, DFD, sequence, ER diagrams from `12` |
| 5 | **Implementation** | 14 | 5.1 tech stack **with justification and rejected alternatives** · 5.2 module walkthrough · 5.3 the AST transformer (annotated code, the hardest part — show it) · 5.4 reducer/inverse reducer · 5.5 lifters · 5.6 shape detection · 5.7 frontend · 5.8 sandbox · 5.9 sample code listings · 5.10 **capability matrix** |
| 6 | **Testing** | 8 | strategy from `14`, the 12 claims table, sample test cases with actual results, adversarial sandbox results, coverage report, screenshots of failures caught |
| 7 | **Results & Evaluation** | 12 | RQ1–RQ5 protocols and **real measured data**; tables and plots; statistical analysis; **a negative-results section** |
| 8 | **Discussion** | 5 | what worked, what did not, where derivation failed and why, threats to validity, comparison back to chapter 2 |
| 9 | **Conclusion & Future Work** | 4 | contributions restated conservatively; `15-AJ` directions |
| — | References (IEEE) | 5 | — |
| — | Appendices | 8 | A: event type reference · B: API reference · C: capability matrix · D: study instruments (quiz, TLX, consent) · E: raw data pointer · F: installation & reproduction guide |

**Two chapters that make this report different from a typical submission:**

- **Chapter 4.5** (execution-strategy comparison) shows you evaluated five approaches and
  chose one with reasons. This is the single strongest signal of engineering maturity
  available to you, and it costs two pages.
- **Chapter 7's negative-results section.** Deliberately reporting the algorithm classes
  where automatic view derivation failed converts a weakness into evidence of rigour.
  Examiners reward this and it is nearly free.

---

## AF. Final Presentation Structure

25 minutes: 15 slides + 7-minute live demo + Q&A.

| # | Slide | Content | Time |
|---|---|---|---|
| 1 | Title | Title, team, guide, institution | 0:20 |
| 2 | **The problem, shown not told** | A student's broken binary search. "Where does `high` become wrong?" Nothing on screen can answer that | 1:00 |
| 3 | Existing tools | Three screenshots: VisuAlgo (can't run your code), Python Tutor (uniform view, no *why*), VS Code (text, forward-only). One honest sentence each | 1:30 |
| 4 | **The idea in one diagram** | `code → events → state → {views, analytics, AI}` — the whole architecture on one slide | 1:00 |
| 5 | Why events | Invertible events buy O(1) step-back; typed events buy derived views; recorded events buy grounded AI. Three consequences of one decision | 1:30 |
| 6 | Architecture | Component diagram, sandbox boundary highlighted in red | 1:30 |
| 7 | How Python is traced | The five options table; one line of before/after transformed code | 1:30 |
| 8 | Sandbox | Layers; the "infinite loop becomes a diagnosable trace, not a hang" point | 1:00 |
| 9 | **The core claim** | "Adding an algorithm changes 0 core files" + the file-diff proof | 1:00 |
| 10 | **DEMO** | 7 minutes, scripted (below) | 7:00 |
| 11 | Time travel | The four-option table; why we chose invertible events + checkpoints; measured seek latency | 1:00 |
| 12 | Grounded AI | Same question, source-only vs grounded, side by side. Show the verifier flagging a false claim | 1:30 |
| 13 | Results | RQ1–RQ5 headline numbers. **Include one negative result** | 2:00 |
| 14 | Limitations | Capability matrix, sandbox threat model, what we did not build. Say it before you are asked | 1:00 |
| 15 | Contributions & future work | Four conservative bullets; the cross-language direction | 1:00 |

**Presentation rules for the team:**
- Slide 2 must land emotionally. Everything after it is justification.
- Never say "any code". Say "the supported subset, defined here".
- The demo is the argument. If time runs short, cut slides 7, 11, 12 — never the demo.
- Rehearse the demo offline (`TemplateExplainer`, cached executions, no network). Assume the
  venue Wi-Fi fails, because it will.

---

## AG. Demo Scenarios

Each scenario states what it *proves*, not just what it shows. The order is a narrative:
generality → recursion → algorithms → the punchline.

### Scenario 1 — Simple program *(90 s)* — proves the engine is real

```python
x = 5
for i in range(5):
    x += i
print(x)
```
Run. Step forward 6 times, watch `x` and `i` change with flash highlights. **Step backward
6 times** — the console output un-prints. Drag the slider to step 3. Then: "no re-execution
happened; this is a recording."

### Scenario 2 — Recursive Fibonacci *(90 s)* — proves the call tree is derived

```python
def fib(n):
    if n <= 1: return n
    return fib(n-1) + fib(n-2)
print(fib(6))
```
Show the call stack growing to depth 6, then the **call-tree view** with the branching
recursion. Point out: `CallTreeView` is the generic view built from `FUNCTION_ENTERED`
events. Show analytics: 25 calls, max depth 6. Ask the AI "why was `fib(2)` called four
times?" Change `fib(6)` to a memoized version and show calls drop to 11.

### Scenario 3 — Binary Search *(120 s)* — proves annotation-free semantics

Load the plugin, run on a 16-element array. The `ArrayView` shows `low`/`high`/`mid`
pointers and a shaded search window — **from `PointerLifter` and `RegionLifter`, not from
plugin code**. Show the source view: the taken branch of the three-way comparison is
underlined. Click `mid` in the variables panel → the timeline filters to its writes.
Ask: *"Why did mid become 4?"* — the causal-chain answer with verified claims.

Then the money moment: **paste the same algorithm as raw text into the editor and run it as
ad-hoc code.** Identical visualization. "The plugin had no special powers."

### Scenario 4 — Merge Sort *(90 s)* — proves divide-and-conquer needs no support

Run on 12 random elements. Show simultaneous views: the array, the call tree, and the
sub-array slices. Watch the merge phase write back. Analytics: comparisons and writes.
Then **benchmark against Bubble Sort** on n = 50/100/200: the comparison table and the
measured growth curves against the stated `O(n log n)` / `O(n²)`.

### Scenario 5 — BFS *(90 s)* — proves views come from structure

Input a graph as a plain adjacency dict — **no graph editor, no special format**:
```python
graph = {'A':['B','C'], 'B':['D'], 'C':['D','E'], 'D':['E'], 'E':[]}
```
`GraphView` appears automatically. Say why: the `AdjacencyMap` detector saw a dict whose
value elements are its own keys. Step through: nodes light up as visited, the queue view
fills and drains from `StackQueueLifter`. Point at the queue panel: "no queue code exists in
this frontend for BFS; it is a generic queue view fed by lifted events."

### Scenario 6 — Dijkstra *(120 s)* — proves heterogeneous simultaneous views

Weighted graph. Three views at once: graph (edges highlight on relaxation), distance table
(cells flash on improvement), priority queue. Step to a decision point and ask the AI:
*"Why did it choose node C next?"* — the answer cites the actual distance values. Show the
grounding report: 5 claims, 5 verified.

### Scenario 7 — **User-created custom algorithm** *(150 s)* — the whole thesis

**This is the most important two minutes of the presentation.** Ask the audience — or the
examiner — to name an algorithm not in the catalog. Type it live. Suggested fallbacks if the
room is silent: Kadane's maximum subarray, insertion sort, DFS with a cycle check, Floyd's
tortoise-and-hare, or the coin-change DP.

Run it. Without touching a single file:
- appropriate views appear (array + DP table, or graph, per structure)
- pointers and regions annotate the interesting indices
- swaps/comparisons are lifted if the code performs them
- analytics count the operations
- the AI explains a step from the actual recording

Then show the terminal: `git status` — clean. **Zero files changed.**

Close with: *"That is the difference between a visualizer and a platform."*

### Scenario 8 — Failure handling *(60 s, optional)* — proves honesty

Run `while True: x += 1`. It does not hang: it stops at the event budget and the student can
**step through the loop that never ends**. Then run code with `import os` → clear denial
message. Then a program using `async def` → the capability banner names the line and the
program still runs with reduced detail.

Including this scenario deliberately is a strong move: it shows the failure modes were
designed rather than discovered.

---

## AG.2 Demo logistics

| Risk | Mitigation |
|---|---|
| Network fails | everything runs on `localhost`; AI falls back to `TemplateExplainer` |
| LLM API is slow/down | pre-cache demo answers by `(execution, step, mode, question)`; fallback is automatic and visible |
| A live-typed algorithm has a bug | that is fine — **run it anyway** and debug it live using the tool. This is the most persuasive possible demo |
| Machine is slow | pre-warm the interpreter; use `granularity=standard`; keep inputs small (≤ 16 elements, ≤ 8 nodes) |
| Docker not available | `SubprocessSandbox` is the default; mention Docker mode on slide 8 |
| Time overrun | scenarios 1, 3, 7 are mandatory; 2, 4, 5, 6, 8 are droppable in that order |
