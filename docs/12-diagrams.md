# 12 — Diagrams (UML, DFD, Sequence)

*(Deliverables T, U, V)*

All diagrams are Mermaid so they render in GitHub, VS Code, and most report toolchains.

---

## T. UML

### T.1 Package / component diagram

```mermaid
graph TD
    subgraph Client["Browser (React + TypeScript)"]
        UI[Panels: Source, Variables, CallStack, Timeline, Console]
        VR[ViewRegistry + generic views]
        TSE[TS Reducer / Timeline mirror]
        ST[ExecutionStore]
        UI --> ST
        VR --> ST
        ST --> TSE
    end

    subgraph Server["Application process (FastAPI)"]
        API[api: REST + WebSocket]
        SVC[services: execution, ai, benchmark]
        LANG[languages: LanguageFrontend registry]
        PY[languages.python: transformer, capabilities, lowering]
        SBX[sandbox: Subprocess / Docker]
        LIFT[lifters: semantic lifting pipeline]
        STATE[state: Reducer, InverseReducer, Timeline]
        SHAPE[shapes: detectors + resolver]
        ANA[analytics: folds, complexity fit]
        AI[ai: context, modes, verifier, clients]
        PLUG[plugins: registry, driver]
        ALGO[(algorithms/*: data only)]
        STORE[store: SQLite + eventlog files]
        CORE[core: Event, EncodedValue, IR]

        API --> SVC
        SVC --> LANG
        SVC --> SBX
        SVC --> LIFT
        SVC --> STATE
        SVC --> ANA
        SVC --> SHAPE
        SVC --> STORE
        SVC --> PLUG
        API --> AI
        LANG --> PY
        PLUG -.discovers.-> ALGO
        PY --> CORE
        STATE --> CORE
        LIFT --> CORE
        SHAPE --> CORE
        ANA --> CORE
        AI --> CORE
    end

    subgraph Child["Sandbox child process / container"]
        RT[runtime: probe, recorder, semantic, policy]
        USER[[instrumented user program]]
        USER --> RT
        RT --> CORE2[core event schema]
    end

    Client <-->|REST| API
    Client <-->|WebSocket| API
    SBX -->|spawn, limits| Child
    Child -->|events.jsonl| STORE
    AI -->|prompt| LLM[(LLM provider)]

    style ALGO fill:#1f2a37,color:#e5e7eb
    style Child fill:#3b1f1f,color:#f3d6d6
    style CORE fill:#12303a,color:#d6f0f3
```

### T.2 Class diagram — event & state model

```mermaid
classDiagram
    class Event {
        +int id
        +int step
        +float t
        +EventType type
        +int frame
        +int depth
        +Loc loc
        +dict payload
        +dict meta
        +to_json() str
        +from_json(s) Event
    }
    class EventType {
        <<enumeration>>
        PROGRAM_STARTED
        LINE_EXECUTED
        VARIABLE_CREATED
        VARIABLE_WRITTEN
        SUBSCRIPT_WRITTEN
        CONDITION_EVALUATED
        FUNCTION_ENTERED
        OBJECT_MUTATED
        ALGORITHM_EVENT
        ...
    }
    class EncodedValue {
        +str kind
        +Any value
        +str ref
        +bool truncated
    }
    class HeapObject {
        +str ref
        +str type_tag
        +int length
        +list items
        +list entries
        +dict fields
    }
    class ExecutionState {
        +int step
        +str status
        +list~Frame~ frames
        +dict~str,HeapObject~ heap
        +str stdout
        +Loc current_loc
        +dict~str,LoopState~ loops
        +dict~str,Annotation~ annotations
        +dict~str,int~ counters
        +active_frame() Frame
        +clone() ExecutionState
    }
    class Frame {
        +int frame_id
        +str func_name
        +int depth
        +dict~str,EncodedValue~ locals
        +EncodedValue return_value
        +bool active
    }
    class Reducer {
        +apply(state, ev) ExecutionState
        +unapply(state, ev) ExecutionState
    }
    class Timeline {
        +list~Event~ events
        +int checkpoint_interval
        +state_at(step) ExecutionState
        +step_forward(s) ExecutionState
        +step_back(s) ExecutionState
        +seek(s, target) ExecutionState
        +next_matching(s, pred) int
    }

    Event --> EventType
    Event ..> EncodedValue : payload contains
    ExecutionState "1" *-- "many" Frame
    ExecutionState "1" *-- "many" HeapObject
    Frame ..> EncodedValue
    Reducer ..> Event
    Reducer ..> ExecutionState
    Timeline *-- Reducer
    Timeline --> Event
```

### T.3 Class diagram — extension points

```mermaid
classDiagram
    class LanguageFrontend {
        <<interface>>
        +str language_id
        +analyze(source) AnalysisResult
        +instrument(source, opts) InstrumentedProgram
        +runtime_bootstrap() str
    }
    class PythonFrontend
    class ShallowPythonFrontend
    class CppFrontend { <<future>> }
    LanguageFrontend <|.. PythonFrontend
    LanguageFrontend <|.. ShallowPythonFrontend
    LanguageFrontend <|.. CppFrontend

    class Sandbox {
        <<interface>>
        +run(job, policy) SandboxResult
    }
    class SubprocessSandbox
    class DockerSandbox
    Sandbox <|.. SubprocessSandbox
    Sandbox <|.. DockerSandbox

    class Lifter {
        <<interface>>
        +str id
        +int window
        +feed(ev, ctx) list~Event~
    }
    class SwapLifter
    class CompareLifter
    class RelaxLifter
    class StackQueueLifter
    Lifter <|.. SwapLifter
    Lifter <|.. CompareLifter
    Lifter <|.. RelaxLifter
    Lifter <|.. StackQueueLifter

    class ShapeDetector {
        <<interface>>
        +detect(obj, state) ShapeMatch
    }
    class AdjacencyMapDetector
    class ScalarArrayDetector
    class LinkedStructureDetector
    ShapeDetector <|.. AdjacencyMapDetector
    ShapeDetector <|.. ScalarArrayDetector
    ShapeDetector <|.. LinkedStructureDetector

    class LLMClient {
        <<interface>>
        +complete(system, user, max_tokens) LLMResponse
    }
    class AnthropicClient
    class TemplateExplainer
    class NullClient
    LLMClient <|.. AnthropicClient
    LLMClient <|.. TemplateExplainer
    LLMClient <|.. NullClient

    class AlgorithmPlugin {
        +str id
        +str name
        +str category
        +str entry
        +list~InputField~ inputs
        +Complexity complexity
        +list~VizHint~ viz_hints
        +list~str~ invariants
    }
    class PluginRegistry {
        +discover() list~AlgorithmPlugin~
        +validate(p) ValidationReport
        +get(id) AlgorithmPlugin
    }
    PluginRegistry o-- AlgorithmPlugin
```

### T.4 State machine — execution lifecycle

```mermaid
stateDiagram-v2
    [*] --> Queued : POST /executions
    Queued --> Analyzing : worker picks up
    Analyzing --> Rejected : UNSUPPORTED and strict mode
    Analyzing --> Instrumenting : capability report ok
    Instrumenting --> ShallowFallback : transformer refused module
    ShallowFallback --> Running
    Instrumenting --> Running : sandbox spawn
    Running --> Running : event batches streamed over WS
    Running --> Finished : program returned
    Running --> Errored : uncaught exception in user code
    Running --> BudgetExceeded : event/time/memory budget hit
    Running --> Killed : cancel or wall-clock timeout
    Finished --> Indexed : lift, reduce, checkpoint, analyze, persist
    Errored --> Indexed
    BudgetExceeded --> Indexed
    Killed --> Indexed
    Indexed --> Navigable
    Navigable --> Navigable : seek / step / AI query
    Rejected --> [*]
    Navigable --> [*] : retention expiry
```

Note that `Errored` and `BudgetExceeded` both reach `Indexed`. A failed run is a
first-class, fully navigable artifact — that is the whole point.

### T.5 Use-case diagram

```mermaid
graph LR
    S((Student))
    I((Instructor))
    P((Plugin author))
    A((Admin))

    S --- UC1[Write and run code]
    S --- UC2[Step forward / backward]
    S --- UC3[Inspect variables and heap]
    S --- UC4[Ask the AI why a value changed]
    S --- UC5[Set breakpoints, step over/into/out]
    S --- UC6[Run a packaged algorithm on custom input]
    S --- UC7[Compare two algorithms on identical input]
    I --- UC8[Share a session link at a specific step]
    I --- UC9[Author an educational walkthrough]
    P --- UC10[Add an algorithm plugin]
    P --- UC11[Add a semantic lifter]
    A --- UC12[Configure sandbox policy and limits]
    A --- UC13[Enable/disable the AI provider]
```

---

## U. Data-Flow Diagrams

### U.1 Level 0 — context

```mermaid
graph LR
    ST((Student)) -->|source, inputs, questions| SYS[AlgoStudio Platform]
    SYS -->|events, state, views, analytics, explanations| ST
    SYS -->|prompt with runtime state| LLM((LLM Provider))
    LLM -->|completion| SYS
    SYS <-->|execution records| DISK[(Execution store: SQLite + event logs)]
    PA((Plugin author)) -->|algorithm plugin directory| SYS
```

### U.2 Level 1 — main processes

```mermaid
graph TD
    ST((Student))
    ST -->|D1 source + inputs| P1[1.0 Analyze and Instrument]
    P1 -->|D2 capability report| ST
    P1 -->|D3 instrumented program| P2[2.0 Execute in Sandbox]
    P2 -->|D4 raw event stream| P3[3.0 Lift Semantic Events]
    P3 -->|D5 enriched event stream| DS1[(DS1 event log + index)]
    DS1 --> P4[4.0 Reduce to State + Checkpoint]
    P4 -->|D6 states, checkpoints| DS2[(DS2 checkpoints)]
    DS1 --> P5[5.0 Compute Analytics]
    P5 -->|D7 metrics| DS3[(DS3 analytics)]
    P4 -->|D8 state at step| P6[6.0 Resolve Views]
    P6 -->|D9 view plan| ST
    P4 -->|D8 state at step| P7[7.0 Render Panels]
    P7 -->|D10 UI| ST
    ST -->|D11 question + step| P8[8.0 Build Grounded Context]
    P4 --> P8
    DS1 --> P8
    P8 -->|D12 prompt| P9[9.0 LLM + Verify Claims]
    P9 -->|D13 answer + grounding report| ST
    P9 --> DS4[(DS4 ai_query log)]
```

### U.3 Level 2 — process 1.0, Analyze and Instrument

```mermaid
graph TD
    A[D1 source text] --> B[1.1 Parse to AST]
    B -->|SyntaxError| Z[1.6 Emit diagnostic] --> OUT2[D2 capability report]
    B --> C[1.2 Resolve scopes]
    C --> D[1.3 Classify capabilities]
    D --> OUT2
    C --> E[1.4 Lower to IR]
    E --> DS[(DS5 IR + source map)]
    D --> F{any UNSUPPORTED and strict?}
    F -->|yes| Z
    F -->|no| G[1.5 Transform AST: insert probes per granularity]
    DS --> G
    G --> H[1.6 Compile to code object]
    H --> OUT3[D3 instrumented program + probe manifest]
    G -->|construct declined| I[emit INSTRUMENTATION_SKIPPED] --> OUT2
```

### U.4 Level 2 — process 2.0, Execute in Sandbox

```mermaid
graph TD
    A[D3 instrumented program] --> B[2.1 Build job dir: source, inputs, policy]
    B --> C[2.2 Spawn isolated child]
    C --> D[2.3 Install limits: rlimits / job object / container flags]
    D --> E[2.4 Install import allowlist + builtins denylist]
    E --> F[2.5 Execute; probes call recorder]
    F --> G[2.6 Encode values, allocate heap refs]
    G --> H[2.7 Append JSONL + byte-offset index]
    H --> DS[(DS1 event log)]
    F --> I{budget exceeded?}
    I -->|yes| J[2.8 Emit BUDGET_EXCEEDED, unwind, flush] --> H
    I -->|no| F
    C --> K[2.9 Watchdog: wall clock, tree kill]
    K --> L[D14 SandboxResult: status, policy_applied, usage]
    H -->|tail| M[2.10 Stream batches over WS]
```

### U.5 Level 2 — process 6.0, Resolve Views

```mermaid
graph TD
    A[D8 state at step] --> B[6.1 Enumerate live heap objects]
    B --> C[6.2 Run every shape detector]
    C --> D[6.3 Collect ShapeMatches per object]
    E[plugin viz_hints] --> F[6.4 Score: detector + hint + liveness + user pin]
    D --> F
    G[user overrides] --> F
    F --> H[6.5 Rank and lay out top N]
    H --> I[6.6 Attach annotations from state]
    I --> J[D9 view plan]
```

---

## V. Sequence Diagrams

### V.1 Run a program end to end

```mermaid
sequenceDiagram
    autonumber
    actor U as Student
    participant FE as Frontend
    participant API as FastAPI
    participant SVC as ExecutionService
    participant LF as PythonFrontend
    participant SB as Sandbox
    participant CH as Child process
    participant LP as LifterPipeline
    participant TL as Timeline/Reducer
    participant DB as Store

    U->>FE: click Run
    FE->>API: POST /api/v1/executions {source, inputs, granularity}
    API->>SVC: create_execution(...)
    SVC->>DB: lookup cache (source_hash, inputs, granularity)
    alt cache hit
        DB-->>SVC: existing execution
        SVC-->>API: 201 {cached: true}
    else cache miss
        SVC->>LF: analyze(source)
        LF-->>SVC: AST, IR, source_map, capability_report
        SVC-->>API: 201 {execution_id, status: running, capability_report}
        API-->>FE: 201 + ws url
        FE->>API: WS connect /ws/executions/{id}
        SVC->>LF: instrument(source, granularity)
        LF-->>SVC: InstrumentedProgram
        SVC->>SB: run(job, policy)
        SB->>CH: spawn (limits, allowlist, clean env)
        loop while executing
            CH->>CH: probes -> recorder -> events.jsonl
            SB-->>SVC: tail new events
            SVC-->>API: batch
            API-->>FE: {"type":"events", events:[...]}
            FE->>FE: append + reduce incrementally, render
        end
        CH-->>SB: exit(status)
        SB-->>SVC: SandboxResult
        SVC->>LP: process(raw events)
        LP-->>SVC: enriched events (+ lifted ALGORITHM_EVENTs)
        SVC->>TL: build(events) -> checkpoints + analytics
        SVC->>DB: persist execution, analytics, event index
        SVC-->>API: finished
        API-->>FE: {"type":"finished", status, analytics_url}
    end
    FE->>U: full timeline navigable
```

### V.2 Step backward (the O(1) path)

```mermaid
sequenceDiagram
    autonumber
    actor U as Student
    participant FE as Frontend
    participant TS as TS Timeline (client)
    participant R as InverseReducer

    U->>FE: press Step Back
    FE->>TS: step_back(currentState)
    TS->>TS: ev = events[state.step]
    TS->>R: unapply(state, ev)
    Note over R: VARIABLE_WRITTEN carries {old,new}<br/>-> restore binding to old, step -= 1
    R-->>TS: previous state
    TS-->>FE: state(step-1)
    FE->>FE: re-render panels + views from state only
    Note over FE: no network call, no re-execution, sub-millisecond
```

### V.3 Seek to an arbitrary step

```mermaid
sequenceDiagram
    autonumber
    actor U as Student
    participant FE as Frontend
    participant TL as Timeline
    participant CP as Checkpoint store
    participant R as Reducer

    U->>FE: drag timeline slider to step 7421
    FE->>TL: seek(state@9002, 7421)
    TL->>TL: backward_cost = 9002-7421 = 1581
    TL->>CP: nearest_checkpoint_at_or_before(7421)
    CP-->>TL: checkpoint@7360
    TL->>TL: forward_cost = 7421-7360 = 61
    Note over TL: 61 < 1581 -> replay from checkpoint
    TL->>R: apply x61 from checkpoint@7360
    R-->>TL: state@7421
    TL-->>FE: state@7421
```

### V.4 Grounded AI explanation

```mermaid
sequenceDiagram
    autonumber
    actor U as Student
    participant FE as Frontend
    participant API as FastAPI
    participant CX as ContextBuilder
    participant TL as Timeline
    participant EL as EventLog
    participant LLM as LLMClient
    participant VF as ClaimVerifier
    participant DB as ai_query

    U->>FE: "Why did mid become 4?" at step 1423
    FE->>API: POST /executions/{id}/ai {step, mode: why_value, focus: mid}
    API->>DB: cache lookup (execution, step, mode, question)
    alt cached
        DB-->>API: prior answer
    else
        API->>CX: build(execution, step=1423, mode, focus="mid")
        CX->>TL: state_at(1423)
        CX->>EL: causal_chain("mid", 1423)
        EL-->>CX: write@41 <- reads low@37, high@12; expr (3+6)//2=4
        CX-->>API: AIContext (token-budgeted, truncation marked)
        API->>LLM: complete(system_rules, context + question)
        LLM-->>API: answer text
        API->>VF: verify(answer, state, analytics)
        VF-->>API: GroundingReport{verified:4, contradicted:0}
        opt contradicted > 0
            API->>LLM: regenerate with contradiction quoted
            LLM-->>API: revised answer
            API->>VF: verify again
        end
        API->>DB: persist query, answer, grounding, tokens
    end
    API-->>FE: {answer, grounding}
    FE->>U: answer with claim underlines + evidence links to events
```

### V.5 Adding a new algorithm (INV-1 in action)

```mermaid
sequenceDiagram
    autonumber
    actor P as Plugin author
    participant FS as Filesystem
    participant REG as PluginRegistry
    participant CAP as CapabilityChecker
    participant API as FastAPI
    participant FE as Frontend
    participant ENG as Execution pipeline
    participant SH as ShapeResolver

    P->>FS: create algorithms/kruskal/{plugin.py, source.py}
    Note over P,FS: no other file in the repository is modified
    REG->>FS: scan algorithms/*/plugin.py
    FS-->>REG: PLUGIN objects
    REG->>CAP: validate(source.py)
    CAP-->>REG: supported
    REG-->>API: catalog entry
    FE->>API: GET /algorithms
    API-->>FE: includes kruskal, with generated input form
    FE->>API: POST /algorithms/kruskal/run {inputs}
    API->>ENG: same pipeline as user-typed code
    ENG-->>SH: state
    SH-->>FE: view plan {graph 0.90, table 0.60}
    Note over FE: GraphView renders — it has never heard of Kruskal
```

### V.6 Sandbox containment of a runaway program

```mermaid
sequenceDiagram
    autonumber
    participant SVC as ExecutionService
    participant SB as Sandbox
    participant CH as Child
    participant PR as Probe/Recorder
    participant WD as Watchdog
    participant FE as Frontend

    SVC->>SB: run(job, policy{max_events:200k, max_seconds:10})
    SB->>CH: spawn with limits
    SB->>WD: arm wall-clock timer
    loop while True: pass
        CH->>PR: _as_line(...) each iteration
        PR->>PR: n += 1
    end
    PR->>PR: n > 200000
    PR->>CH: emit BUDGET_EXCEEDED, flush, raise ExecutionBudgetExceeded
    CH->>CH: unwind stack, close event file
    CH-->>SB: exit(3)
    SB->>WD: disarm
    SB-->>SVC: SandboxResult{status: budget_exceeded, events_path}
    SVC-->>FE: finished(partial=true, 200000 events)
    Note over FE: student can now step through the loop<br/>and see exactly why it never terminates
    alt child ignores the exception (hostile code)
        WD->>WD: 10s elapsed
        WD->>CH: terminate process group / job object
        SB-->>SVC: SandboxResult{status: killed}
    end
```

### V.7 Live WebSocket delivery with reconnect

```mermaid
sequenceDiagram
    autonumber
    participant FE as Frontend
    participant WS as WS hub
    participant TAIL as Event tailer
    participant LOG as events.jsonl

    FE->>WS: connect, {"type":"subscribe","from_event":0}
    WS-->>FE: {"type":"hello", status:"running"}
    TAIL->>LOG: read new lines
    TAIL->>WS: batch [0..511]
    WS-->>FE: {"type":"events","from":0,"to":512}
    Note over FE: network drops
    FE->>WS: reconnect, {"type":"subscribe","from_event":512}
    WS->>LOG: seek via events.idx to offset(512)
    WS-->>FE: {"type":"events","from":512,...} (no state to recover)
    TAIL->>WS: EOF + child exited
    WS-->>FE: {"type":"finished","event_count":8412}
```
