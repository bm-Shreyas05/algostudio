# 15 — Research Methodology, Evaluation Metrics, Research Gap, Literature Survey

*(Deliverables Z, AA, AC, AD, AJ; §37, §38 of the brief)*

**Standing rule for this project: no fabricated results.** Every table in this document has
empty result columns. They are filled by running the protocols described here. A synopsis
that reports numbers before the experiments have run is worthless, and a reviewer will find
it.

---

## Z. Research Methodology

### Z.1 Research questions

| RQ | Question | Type | Falsifiable prediction |
|---|---|---|---|
| **RQ1** | Can a single generic event model support useful visualization across structurally different algorithm classes (search, sort, graph, DP, recursion) without algorithm-specific rendering code? | Constructive + expert evaluation | If false, some class will require a hand-authored view; we will report which and why |
| **RQ2** | Does synchronized, reversible execution state improve comprehension and debugging accuracy relative to static/animated presentation? | Controlled experiment | Grounded in the "step back" affordance; may show no effect |
| **RQ3** | Does grounding LLM explanations in recorded runtime state reduce factually incorrect claims about the execution? | Controlled experiment | Contradiction rate lower with grounding; effect size unknown |
| **RQ4** | What is the engineering cost of adding an algorithm under the plugin architecture? | Repeated-measures engineering study | Files-outside-plugin-dir = 0; LOC and time to be measured |
| **RQ5** | How does event granularity trade off against execution overhead and perceived usefulness? | Benchmark + rating study | Monotone overhead increase; usefulness expected non-monotone (verbose may *hurt*) |

RQ1 and RQ4 are the ones the architecture is designed to answer, and both are answerable
with the artifact alone. RQ2 and RQ3 need human participants.

### Z.2 RQ1 — coverage study

**Design.** Constructive evaluation with independent expert rating.

1. Select 20 algorithms spanning 6 classes: search (2), comparison sort (4), non-comparison
   sort (2), graph traversal/shortest-path/MST (5), dynamic programming (3), tree/BST (2),
   string (2). Selection is fixed **before** any is implemented, from a standard syllabus, to
   prevent choosing algorithms that suit the system.
2. Implement each as a plugin, recording effort (feeds RQ4).
3. For each, capture the resulting visualization at 5 evenly spaced steps.
4. Three independent raters (course instructors, not team members) score each on a 5-point
   rubric: *Does the visualization make the algorithm's key state and operation visible at
   this step?* Rubric anchors are written and piloted before rating.
5. Report per-class mean, inter-rater agreement (Krippendorff's α), and — most importantly —
   **the algorithms that scored ≤ 2, with an analysis of why derivation failed.**

**Ablation:** re-rate with the lifter pipeline disabled, isolating the contribution of
semantic lifting versus generic events alone.

**Threat to validity:** raters know the system is ours. Mitigation: they rate screenshots
without knowing which algorithm class we predicted would be hard, and the control (a
published curated visualizer's rendering of the same algorithm) is rated in the same session.

### Z.3 RQ2 — comprehension experiment

**Design.** Between-subjects, 3 conditions, pre-registered analysis plan.

| Condition | Tool |
|---|---|
| C1 (control) | Static slides + a curated animation of the same algorithm |
| C2 | AlgoStudio, **forward-only** (step-back disabled) |
| C3 | AlgoStudio, full time travel |

C2 exists specifically to isolate reversibility from the rest of the system. Without it, a
positive result only says "our tool beats slides", which is uninteresting.

**Participants.** 45+ second-year CS students (15/condition), randomized, stratified by a
prior-knowledge pre-test.

**Tasks.**
1. *Comprehension* — 10 questions about a shown execution (predict next value, identify
   which line changed a variable, state the loop invariant). Score = correct/10.
2. *Debugging* — 3 subtly broken programs (off-by-one in binary search, wrong swap index in
   partition, missing visited-check in BFS). Measure: located the bug (y/n), time to locate,
   correct fix (y/n).
3. *Transfer* — explain a related algorithm not seen during the session.

**Measures.** Accuracy, time-on-task, NASA-TLX cognitive load, self-reported confidence,
and confidence×accuracy calibration (a tool that raises confidence without accuracy is a
negative result worth reporting).

**Analysis.** Pre-registered: one-way ANOVA on comprehension, Kruskal–Wallis on time,
planned contrasts C3 vs C2 (reversibility) and C2 vs C1 (the platform). α = 0.05,
Holm correction. Effect sizes (η², Cliff's δ) reported regardless of significance.

**Threats.** Novelty effect (mitigated: 15-minute standardized tutorial in every condition,
including C1). Experimenter bias (mitigated: scripted session, automated scoring).
Small n (acknowledged: this is a pilot; we report CIs and treat it as such).

### Z.4 RQ3 — AI grounding experiment

**Design.** Within-subjects on *questions*, 4 conditions, fully automated — no human
participants needed for the primary measure, which makes it the most reliably completable
study in the set.

| Condition | Prompt contents |
|---|---|
| A1 | source code only |
| A2 | source + final output |
| A3 | source + **grounded runtime context** (AlgoStudio `AIContext`) |
| A4 | A3 + verifier-with-retry |
| A5 | `TemplateExplainer` (deterministic, 100% grounded by construction) |

**Materials.** 150 questions over 30 executions (5 per execution), spanning modes
`why_value`, `why_branch`, `what_changed`, `why_called`, `complexity`. Ground truth for
every question is computed *from the event stream*, so the answer key is exact and
automatic — this is the methodological advantage the engine provides.

**Measures.**
- **Contradiction rate** — claims contradicted by state (primary; automated).
- **Unverifiable rate** — claims the verifier could not check.
- **Correctness** — human-rated on a 50-question stratified subsample, two raters blind to
  condition.
- **Verifier recall** — on a hand-labelled sample of 100 answers, what fraction of actually
  false claims the verifier catches. **Reported alongside the contradiction rate**, because a
  contradiction rate without detector recall is not interpretable.
- Cost: tokens, latency.

**Analysis.** McNemar / Cochran's Q across conditions on the same questions.

### Z.5 RQ4 — plugin effort study

Repeated-measures over the 20 algorithms from RQ1, with two implementers (one who built the
platform, one who did not — the difference between them estimates the "insider advantage"
and is itself the interesting number).

Per algorithm, recorded automatically where possible: wall-clock time from `git` timestamps,
LOC in `plugin.py` and `source.py`, **files changed outside `algorithms/<id>/`** (must be 0),
number of `algo.*` annotations needed, whether any core change was *wanted* (recorded even
when worked around — a suppressed desire to touch core is evidence of a leak in the design).

**Baseline for comparison:** implement 3 of the same algorithms as hand-authored animations
in a comparable framework (e.g. a d3-based custom animation) and measure the same variables.
Without this baseline, "it took 40 minutes" means nothing.

### Z.6 RQ5 — granularity study

Two halves.

*Quantitative (automated):* for each of 15 programs × 3 granularities × 5 input sizes,
measure overhead ratio, events emitted, bytes, reducer throughput, and end-to-end latency.
10 repetitions, report median and IQR, warm interpreter, pinned CPU where possible.

*Qualitative:* 12 students rate the same execution at each granularity on usefulness and
overwhelm (counterbalanced order). The hypothesis worth testing is that **verbose is worse
for learning despite being strictly more informative** — an interesting result either way.

### Z.7 Reproducibility

Every experiment ships as a script under `research/`: fixed seeds, pinned dependencies,
recorded hardware, raw data committed as CSV, analysis notebooks committed. Ethics approval
obtained from the institutional committee for RQ2/RQ5-qualitative; informed consent; no
personally identifying data retained.

---

## AA. Evaluation Metrics

### System performance

| Metric | Definition | Method | Target | Result |
|---|---|---|---|---|
| Instrumentation overhead | `t_instr / t_native` | 15 programs × 3 granularities × 10 reps | < 5x / 25x / 120x | *(TBM)* |
| Event throughput | events/sec emitted | same | > 100k @ standard | *(TBM)* |
| Event size | mean bytes/event | over the corpus | < 220 B | *(TBM)* |
| Reduction throughput | steps/sec (Python) | 100k-event trace | > 200k/s | *(TBM)* |
| `state_at(n)` latency | ms, n = 1k/10k/100k, K=64 | 50 reps | < 5 ms | *(TBM)* |
| Step-back latency | ms | 1000 reps | < 0.1 ms | *(TBM)* |
| Checkpoint memory | MB per 10k steps | vary K ∈ {16,64,256} | < 25 MB | *(TBM)* |
| End-to-end latency | POST → `finished`, 5k-event program | 20 reps, both sandbox modes | < 1.5 s subprocess | *(TBM)* |
| Visualization latency | step → repaint (frontend) | Performance API, 500 steps | < 16 ms (60 fps) | *(TBM)* |
| Sandbox start overhead | subprocess vs Docker | 50 reps | report both | *(TBM)* |
| Memory ceiling honoured | peak child RSS vs limit | adversarial suite | 100% | *(TBM)* |

### Educational

| Metric | Instrument | Result |
|---|---|---|
| Comprehension accuracy | 10-item quiz, per condition | *(TBM)* |
| Debugging success rate | 3 seeded bugs, located + fixed | *(TBM)* |
| Time to locate a bug | seconds, per condition | *(TBM)* |
| Cognitive load | NASA-TLX | *(TBM)* |
| Confidence calibration | confidence vs accuracy correlation | *(TBM)* |
| Feature use | step-back invocations per session (logged) | *(TBM)* |

### Engineering

| Metric | Definition | Target | Result |
|---|---|---|---|
| **Core files changed per new algorithm** | files outside `algorithms/<id>/` in the diff | **0** | *(TBM)* |
| Plugin LOC | `plugin.py` + `source.py` | < 120 median | *(TBM)* |
| Time to add an algorithm | wall clock, insider vs outsider | report both | *(TBM)* |
| Views reused per new algorithm | existing view components used | ≥ 1, 0 new | *(TBM)* |
| Cyclomatic complexity of the renderer | radon/eslint on `views/` | no growth with algorithm count | *(TBM)* |
| Capability coverage | supported constructs / tested constructs | published matrix | *(TBM)* |

The first row is the project's headline number.

### AI

| Metric | Definition | Result |
|---|---|---|
| Contradiction rate | claims contradicted by state / total claims | *(TBM)* |
| Unverifiable rate | claims the verifier cannot check | *(TBM)* |
| **Verifier recall** | true false-claims caught / true false-claims present | *(TBM)* |
| Human-rated correctness | 5-point, blind, 2 raters, κ reported | *(TBM)* |
| Refusal appropriateness | correct "the trace doesn't show that" / all such | *(TBM)* |
| Cost | tokens in/out, ¢/query, latency | *(TBM)* |

---

## AC. Research Gap

A precise statement of what is and is not novel. Overclaiming here is the fastest way to
lose a viva.

**Not novel — prior art exists and is acknowledged:**
- Execution tracing and instrumentation (decades of debugger and profiler work).
- Program visualization from real execution (Python Tutor, and the algorithm-animation
  literature going back to BALSA and Zeus in the 1980s).
- Omniscient / back-in-time debugging (ODB, TOD, `rr`, Chronon, and Elm's time-travelling
  debugger).
- Event sourcing (a standard enterprise pattern).
- LLM-based code explanation and retrieval-grounded generation.

**The gap:** these lines of work have not been **composed**. Specifically:

1. **Omniscient debugging exists for engineers, not learners.** `rr` and TOD give perfect
   reverse execution but present it through a professional debugger UI and produce no
   pedagogical abstraction. Nobody has asked whether reverse execution *teaches*.
2. **Algorithm visualization is authored; execution visualization is uniform.** No system
   attempts to *derive* algorithm-class-appropriate views from structural properties of
   runtime state. The systems that show arrays as arrays were told to; the systems that
   derive their display show everything the same way.
3. **Semantic lifting from generic traces is unexplored in this domain.** Recovering
   `swap`/`compare`/`relax` from low-level events by idiom matching — rather than
   annotation or hard-coding — appears to be genuinely new in educational visualization.
4. **AI explanation of program execution is not grounded in recorded execution.** Current
   tools ground in *source*; grounding in a *specific run*, with automated verification of
   claims against that run, is not established practice — and the verification step is what
   makes it measurable rather than merely plausible.

**The contribution, stated conservatively:**

> An event model and reducer design that makes visualization, time travel, analytics, and
> verifiable AI explanation *derivable* from a single execution recording — together with an
> empirical evaluation of how far derivation actually goes, including where it fails.

The honest framing is that this is a **systems and composition contribution with an
empirical evaluation**, not a new algorithm. That is an appropriate and defensible level of
novelty for a final-year project, and it is strengthened, not weakened, by reporting the
algorithm classes where derivation does not work.

---

## AD. Literature Survey Topics

Organized as the report's chapter 2, with the specific question each section must answer.

1. **Program visualization & algorithm animation** — BALSA, Zeus, TANGO, Jeliot, JHAVÉ,
   ANIMAL, VisuAlgo, Python Tutor. *Question: which are authored and which are derived, and
   what did each give up for that choice?*
2. **Effectiveness of algorithm visualization** — Hundhausen, Douglas & Stasko's
   meta-study; the "engagement taxonomy" (Naps et al.). *Question: the field's own finding
   that passive viewing does not help while active engagement does — how does our design
   respond to it?* (This is the most important section: it is the strongest existing
   evidence and it constrains our claims.)
3. **Omniscient / back-in-time debugging** — Lienhard's ODB, TOD, `rr`, Chronon, Elm.
   *Question: what recording and replay strategies were used, and at what cost?*
4. **Dynamic analysis & instrumentation** — source vs bytecode vs VM-level; Pin, Valgrind,
   DynamoRIO; Python's `sys.settrace`/`sys.monitoring`/PEP 669. *Question: what does each
   granularity make observable, and what does it cost?*
5. **Execution trace compression & querying** — trace slicing, dynamic program slicing
   (Korel & Laski), provenance. *Question: how do others answer "why does this variable have
   this value?"* — directly relevant to our causal chain.
6. **Event sourcing & CQRS** — Fowler, Young. *Question: what is known about snapshotting
   intervals and inverse events?*
7. **Sandboxing untrusted code** — seccomp, gVisor, Firecracker, WASM/Pyodide; the history
   of `rexec`'s removal from Python. *Question: what is a defensible boundary, and what is
   known not to work?*
8. **Automatic data-structure recovery** — shape analysis, DDT/`Howard`-style dynamic type
   inference, heap-graph abstraction. *Question: what techniques exist for classifying heap
   structures at runtime?* — the academic grounding for our shape detectors.
9. **Notional machines & CS-education theory** — Sorva's work on notional machines and
   program-state visualization; misconception literature on aliasing and recursion.
   *Question: which misconceptions does a state visualization actually address?*
10. **LLMs for code comprehension & tutoring** — code explanation, feedback generation, the
    hallucination literature, grounding/RAG, verifier-augmented generation.
    *Question: what is known about grounding reducing factual error in code explanation?*
11. **Automated assessment & feedback in CS1/CS2** — where an execution record could
    contribute beyond visualization.
12. **Plugin & extension architectures** — for the INV-1 discussion.

Target: 45–60 references, ≥ 60% from peer-reviewed venues (SIGCSE, ICER, ITiCSE, VL/HCC,
ICSE, OOPSLA, TOCE, Computers & Education).

---

## AJ. Future Research Directions

1. **Cross-language execution equivalence.** With two frontends, the same algorithm in
   Python and C++ produces two event streams. Can they be *aligned* into one timeline?
   That would make language-independent algorithm teaching concrete, and the alignment
   problem (trace matching under differing granularity) is a genuine research question.
2. **Learned view resolution.** Replace hand-tuned detector scores with a model trained on
   user override behaviour. The dataset is generated by ordinary use.
3. **Automatic invariant discovery.** Daikon-style inference over the recorded state stream
   to propose loop invariants — then *check* them against the recording. Grounded invariant
   suggestion is directly useful pedagogically and is a natural fit for the event log.
4. **Trace-based misconception detection.** Compare a student's execution against a reference
   execution of the same algorithm and classify the divergence into a misconception taxonomy.
   The alignment machinery from (1) is the enabler.
5. **Adaptive granularity.** Instrument finely only where the student is looking or where a
   divergence occurred; re-run with higher granularity on demand. Turns the RQ5 trade-off
   into a control loop.
6. **Trace compression & indexing at scale.** Structural compression of repetitive loop
   events; queryable trace indexes for "show me every step where `low > high`".
7. **Client-side execution via WASM.** Pyodide moves the sandbox into the browser, removing
   the server threat model entirely and making the platform deployable as a static site — a
   significant change to the security and scaling story.
8. **Grounded tutoring beyond explanation.** Using the recording to generate *targeted
   exercises* ("fix this program so that the loop terminates") with automatic verification of
   the student's fix by re-execution and event comparison.
