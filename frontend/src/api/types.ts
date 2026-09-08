/**
 * Mirror of backend/algostudio/core/events.py and state/model.py.
 *
 * This file and its Python counterpart are the cross-language contract
 * (docs/11 §S.2, `shared/`). `tests/integration/test_reducer_parity.py` runs
 * fixture executions through both reducers and compares the resulting JSON, so
 * a drift here fails CI rather than silently showing the user a state that
 * never existed.
 */

export type EventTypeName =
  | "PROGRAM_STARTED" | "PROGRAM_FINISHED" | "STDOUT_WRITE" | "STDERR_WRITE"
  | "STDIN_READ" | "LINE_EXECUTED" | "CONDITION_EVALUATED" | "BRANCH_TAKEN"
  | "LOOP_STARTED" | "LOOP_ITERATION" | "LOOP_FINISHED" | "FUNCTION_ENTERED"
  | "FUNCTION_RETURNED" | "FUNCTION_EXITED" | "EXCEPTION_RAISED"
  | "EXCEPTION_HANDLED" | "VARIABLE_CREATED" | "VARIABLE_WRITTEN"
  | "VARIABLE_READ" | "VARIABLE_DELETED" | "SUBSCRIPT_READ"
  | "SUBSCRIPT_WRITTEN" | "SUBSCRIPT_DELETED" | "ATTRIBUTE_READ"
  | "ATTRIBUTE_WRITTEN" | "OBJECT_CREATED" | "OBJECT_MUTATED" | "OBJECT_FREED"
  | "EXPRESSION_EVALUATED" | "COLLECTION_CREATED" | "COLLECTION_RESIZED"
  | "STACK_PUSH" | "STACK_POP" | "QUEUE_ENQUEUE" | "QUEUE_DEQUEUE"
  | "ALGORITHM_EVENT" | "BUDGET_WARNING" | "BUDGET_EXCEEDED"
  | "INSTRUMENTATION_SKIPPED" | "SNAPSHOT";

export interface Loc {
  line: number;
  col: number;
  end_line: number;
  end_col: number;
}

export interface AsEvent {
  id: number;
  step: number;
  type: EventTypeName;
  t: number;
  frame: number;
  depth: number;
  loc?: Loc;
  payload: Record<string, any>;
  meta?: Record<string, any>;
}

/** Encoded value: primitives inline, containers by reference into the heap. */
export type EncodedValue =
  | { k: "int" | "float"; v: number | null; special?: string }
  | { k: "bool"; v: boolean }
  | { k: "str"; v: string; len?: number; trunc?: boolean }
  | { k: "none" }
  | { k: "ref"; r: string; t: string; n: number; trunc?: boolean }
  | { k: "opaque"; t: string; repr: string }
  | { k: "cycle"; r: string };

export interface HeapObject {
  ref: string;
  t: string;
  n?: number;
  items?: EncodedValue[];
  entries?: [EncodedValue, EncodedValue][];
  fields?: Record<string, EncodedValue>;
  cls?: string;
  trunc?: boolean;
}

export interface Frame {
  frame_id: number;
  func_id: string;
  name: string;
  depth: number;
  call_line: number;
  line: number;
  args: string[];
  locals: Record<string, EncodedValue>;
  return_value: EncodedValue | null;
  active: boolean;
  parent: number;
  exit_reason: string;
}

export interface LoopState {
  loop_id: string;
  kind: string;
  line: number;
  iteration: number;
  finished: boolean;
  exit: string;
}

export interface Annotation {
  event_id: number;
  step: number;
  kind: string;
  target_ref: string | null;
  label: string;
  color: string;
  index: number | null;
  lo: number | null;
  hi: number | null;
  value: Record<string, any>;
  ttl: number;
}

export interface CallRecord {
  frame_id: number;
  parent: number;
  name: string;
  func_id: string;
  depth: number;
  call_line: number;
  enter_step: number;
  args: Record<string, EncodedValue>;
  return_value: EncodedValue | null;
  exit_step: number;
  exit_reason: string;
}

export interface ExceptionInfo {
  exc_type: string;
  message: string;
  line: number;
  handled: boolean;
}

export interface ExecutionState {
  step: number;
  status: string;
  frames: Frame[];
  retired: Record<number, Frame>;
  heap: Record<string, HeapObject>;
  stdout: string;
  stderr: string;
  current_loc: Loc | null;
  loops: Record<string, LoopState>;
  exception: ExceptionInfo | null;
  annotations: Record<number, Annotation>;
  counters: Record<string, number>;
  call_tree: CallRecord[];
  finished_reason: string;
}

export interface CapabilityIssue {
  line: number;
  col: number;
  severity: "ok" | "partial" | "degraded" | "unsupported";
  code: string;
  message: string;
  construct: string;
}

export interface CapabilityReport {
  supported: boolean;
  issues: CapabilityIssue[];
}

export interface ViewDescriptor {
  ref: string;
  view: string;
  score: number;
  reason: string;
  name: string;
  kind: string;
  props: Record<string, any>;
  alternatives: { view: string; score: number; reason: string }[];
  primary: boolean;
}

export interface Analytics {
  metrics: Record<string, number>;
  line_hits: Record<string, number>;
  algorithm_events: Record<string, number>;
  function_calls: Record<string, number>;
  max_depth: number;
  peak_heap_objects: number;
  event_count: number;
  duration_ms: number;
  events_per_category: Record<string, number>;
  event_origins: { recorded: number; lifted: number; semantic: number };
}

export interface ExecutionSummary {
  execution_id: string;
  status: string;
  language: string;
  algorithm_id: string | null;
  granularity: string;
  event_count: number;
  wall_ms: number;
  peak_rss_mb: number | null;
  sandbox_mode: string;
  policy_applied: Record<string, boolean>;
  capability_report: CapabilityReport;
  error: { type: string; message: string; line?: number } | null;
  source: string;
  inputs: Record<string, any>;
  source_map: Record<string, any>;
  structure: Record<string, any>;
  lifters: boolean;
}

export interface AlgorithmInputField {
  name: string;
  kind: string;
  default: any;
  description: string;
  required: boolean;
}

export interface AlgorithmPlugin {
  id: string;
  name: string;
  category: string;
  description: string;
  entry: string;
  inputs: AlgorithmInputField[];
  complexity: { time: string; space: string; best: string; worst: string } | null;
  metrics: string[];
  viz_hints: { target: string; view: string; weight: number }[];
  invariants: string[];
  tags: string[];
  annotated: boolean;
  source?: string;
  explanation?: string;
}

export interface Claim {
  text: string;
  kind: string;
  subject: string;
  claimed: string;
  verified: boolean;
  contradicted: boolean;
  actual: string;
  evidence_step: number | null;
}

export interface GroundingReport {
  score: number;
  verified: number;
  unverified: number;
  contradicted: number;
  claims: Claim[];
  note: string;
}

export interface AIAnswer {
  answer: string;
  provider: string;
  model: string;
  grounding: GroundingReport;
  context_summary?: Record<string, number>;
  notice?: string;
  cached: boolean;
  mode: string;
  step: number;
  latency_ms?: number;
}
