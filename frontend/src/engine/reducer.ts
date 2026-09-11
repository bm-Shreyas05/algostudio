/**
 * R and R' in TypeScript -- a mirror of backend/algostudio/state/reducer.py.
 *
 * Why duplicate the reducer at all: navigation (step, seek, play) then needs no
 * network round trip, so scrubbing the timeline is instant instead of ~30 ms
 * per frame. The duplication is a real risk, so it is tested: fixture
 * executions run through both reducers and the canonical JSON must match.
 *
 * The copy-on-write discipline from the Python side applies here too. Nothing
 * is mutated in place, because checkpoints share structure with live states.
 */

import type {
  AsEvent, Annotation, CallRecord, EncodedValue, ExecutionState, Frame,
  HeapObject, LoopState,
} from "../api/types";

const INFINITE_TTL = 1e9;

/** Never a useful label: `self` is bound in __init__, the earliest frame to
 *  see the object, so it would otherwise claim the name of every instance. */
const UNINFORMATIVE_NAMES = new Set(["self", "cls", "_"]);

const ANNOTATION_TTL: Record<string, number> = {
  // In events, but the default step is a source line (5-15 events), so short
  // TTLs expired before the user ever saw the highlight.
  compare: 14, highlight: 14, swap: 14, relax: 18, discover: 26, note: 26,
  push: 14, pop: 14, enqueue: 14, dequeue: 14,
  pointer: INFINITE_TTL, region: INFINITE_TTL, mark: INFINITE_TTL,
  visit: INFINITE_TTL, pivot: INFINITE_TTL, partition: INFINITE_TTL,
  nodevalue: INFINITE_TTL,
};

/** Which argument identifies what an annotation is about. Mirrors
 *  model.SUBJECT_ARGS: without it every `visit` shares one key and a graph can
 *  only ever show its most recently visited node. */
const SUBJECT_ARGS: Record<string, string[]> = {
  visit: ["node"], discover: ["node"], mark: ["target"], unmark: ["target"],
  highlight: ["index"], compare: ["i", "j"], swap: ["i", "j"],
  relax: ["u", "v"], enqueue: ["value"], push: ["value"],
  nodevalue: ["node"],
};

function annotationSubject(kind: string, args: Record<string, any>): string {
  const keys = SUBJECT_ARGS[kind];
  if (!keys) return "";
  return keys
    .map((key) => {
      const value = args[key];
      const scalar =
        value && typeof value === "object" ? (value.v ?? value.r) : value;
      return scalar === undefined || scalar === null ? "" : String(scalar);
    })
    .join("|");
}

const ANNOTATION_KINDS = new Set([
  "pointer", "region", "mark", "unmark", "highlight", "visit", "discover",
  "compare", "swap", "relax", "pivot", "partition", "note",
  "push", "pop", "enqueue", "dequeue", "nodevalue",
]);

const COUNTER_FOR: Partial<Record<string, string>> = {
  LINE_EXECUTED: "statements",
  VARIABLE_WRITTEN: "variable_writes",
  VARIABLE_CREATED: "variable_writes",
  VARIABLE_READ: "variable_reads",
  SUBSCRIPT_READ: "array_reads",
  SUBSCRIPT_WRITTEN: "array_writes",
  FUNCTION_ENTERED: "function_calls",
  LOOP_ITERATION: "loop_iterations",
  CONDITION_EVALUATED: "conditions",
  OBJECT_MUTATED: "mutations",
};

export function initialState(): ExecutionState {
  return {
    step: -1,
    status: "running",
    frames: [{
      frame_id: 0, func_id: "<module>", name: "<module>", depth: 0,
      call_line: 0, line: 0, args: [], locals: {}, return_value: null,
      active: true, parent: -1, exit_reason: "",
    }],
    retired: {},
    heap: {},
    stdout: "",
    stderr: "",
    current_loc: null,
    loops: {},
    exception: null,
    annotations: {},
    counters: {},
    call_tree: [],
    finished_reason: "",
  };
}

export function cloneState(s: ExecutionState): ExecutionState {
  return {
    ...s,
    frames: s.frames.map((f) => ({ ...f })),
    retired: { ...s.retired },
    heap: { ...s.heap },
    loops: Object.fromEntries(Object.entries(s.loops).map(([k, v]) => [k, { ...v }])),
    annotations: { ...s.annotations },
    counters: { ...s.counters },
    call_tree: [...s.call_tree],
  };
}

// ---------------------------------------------------------------------------
export function apply(s: ExecutionState, ev: AsEvent): ExecutionState {
  forward(s, ev);
  if (ev.loc) {
    s.current_loc = ev.loc;
    setFrameLine(s, ev.frame, ev.loc.line);
  }
  const counter = COUNTER_FOR[ev.type];
  if (counter) s.counters[counter] = (s.counters[counter] ?? 0) + 1;
  s.step = ev.id;
  return s;
}

export function unapply(s: ExecutionState, ev: AsEvent, prev: AsEvent | null): ExecutionState {
  inverse(s, ev);
  const counter = COUNTER_FOR[ev.type];
  if (counter) {
    s.counters[counter] = (s.counters[counter] ?? 0) - 1;
    if (s.counters[counter] <= 0) delete s.counters[counter];
  }
  if (ev.loc) {
    const prevLine = (ev.meta?.pl as number) ?? 0;
    s.current_loc = prevLine
      ? { line: prevLine, col: 0, end_line: prevLine, end_col: 0 }
      : null;
    setFrameLine(s, ev.frame, (ev.meta?.pfl as number) ?? 0);
  }
  s.step = prev ? prev.id : -1;
  return s;
}

/** Attribute a line to the frame the event belongs to, not the stack top. */
function setFrameLine(s: ExecutionState, frameId: number, line: number): void {
  for (let i = s.frames.length - 1; i >= 0; i--) {
    if (s.frames[i].frame_id === frameId) {
      s.frames[i] = { ...s.frames[i], line };
      return;
    }
  }
}

function targetFrame(s: ExecutionState, ev: AsEvent): Frame {
  if (ev.payload.scope === "global") return s.frames[0];
  for (let i = s.frames.length - 1; i >= 0; i--) {
    if (s.frames[i].frame_id === ev.frame) return s.frames[i];
  }
  return s.frames[s.frames.length - 1];
}

function bind(s: ExecutionState, frame: Frame, name: string, value: EncodedValue): void {
  const index = s.frames.indexOf(frame);
  const next = { ...frame, locals: { ...frame.locals, [name]: value } };
  if (index >= 0) s.frames[index] = next;
}

function unbind(s: ExecutionState, frame: Frame, name: string): void {
  const index = s.frames.indexOf(frame);
  const locals = { ...frame.locals };
  delete locals[name];
  const next = { ...frame, locals };
  if (index >= 0) s.frames[index] = next;
}

function heapCopy(s: ExecutionState, ref: string | undefined): HeapObject | null {
  if (!ref) return null;
  const rec = s.heap[ref];
  if (!rec) return null;
  const next: HeapObject = { ...rec };
  if (rec.items) next.items = [...rec.items];
  if (rec.entries) next.entries = rec.entries.map((e) => [...e] as [EncodedValue, EncodedValue]);
  if (rec.fields) next.fields = { ...rec.fields };
  return next;
}

function keyEquals(encoded: EncodedValue, index: any): boolean {
  const v = (encoded as any)?.v;
  return v === index || String(v) === String(index);
}

function encodeKey(index: any): EncodedValue {
  if (typeof index === "boolean") return { k: "bool", v: index };
  if (typeof index === "number") {
    return Number.isInteger(index) ? { k: "int", v: index } : { k: "float", v: index };
  }
  return { k: "str", v: String(index), len: String(index).length };
}

function setIndex(
  s: ExecutionState, ref: string | undefined, index: any, value: EncodedValue,
  insert = false, position: number | null = null,
): void {
  const rec = heapCopy(s, ref);
  if (!rec || !ref) return;
  if (rec.items || ["list", "tuple", "deque", "array"].includes(rec.t)) {
    const items = rec.items ?? (rec.items = []);
    if (typeof index !== "number") return;
    const pos = index >= 0 ? index : (rec.n ?? items.length) + index;
    if (pos >= items.length && rec.trunc) return;
    if (insert || pos >= items.length) {
      const at = Math.max(0, Math.min(position ?? pos, items.length));
      items.splice(at, 0, value);
      rec.n = (rec.n ?? items.length - 1) + 1;
    } else {
      items[pos] = value;
      rec.n = Math.max(rec.n ?? 0, items.length);
    }
  } else {
    const entries = rec.entries ?? (rec.entries = []);
    const found = entries.findIndex((pair) => keyEquals(pair[0], index));
    if (found >= 0) entries[found] = [entries[found][0], value];
    else {
      const at = Math.max(0, Math.min(position ?? entries.length, entries.length));
      entries.splice(at, 0, [encodeKey(index), value]);
    }
    rec.n = entries.length;
  }
  s.heap[ref] = rec;
}

function deleteIndex(s: ExecutionState, ref: string | undefined, index: any): void {
  const rec = heapCopy(s, ref);
  if (!rec || !ref) return;
  if (rec.items) {
    if (typeof index === "number") {
      const pos = index >= 0 ? index : rec.items.length + index;
      if (pos >= 0 && pos < rec.items.length) rec.items.splice(pos, 1);
    }
    rec.n = rec.items.length;
  } else if (rec.entries) {
    rec.entries = rec.entries.filter((pair) => !keyEquals(pair[0], index));
    rec.n = rec.entries.length;
  }
  s.heap[ref] = rec;
}

function updateCall(s: ExecutionState, frameId: number, changes: Partial<CallRecord>): void {
  for (let i = s.call_tree.length - 1; i >= 0; i--) {
    if (s.call_tree[i].frame_id === frameId) {
      s.call_tree[i] = { ...s.call_tree[i], ...changes };
      return;
    }
  }
}

// ---------------------------------------------------------------------------
function forward(s: ExecutionState, ev: AsEvent): void {
  const p = ev.payload;
  switch (ev.type) {
    case "PROGRAM_STARTED":
      s.status = "running";
      break;
    case "PROGRAM_FINISHED":
      s.status = p.status ?? "ok";
      s.finished_reason = p.status ?? "";
      break;
    case "BUDGET_EXCEEDED":
      s.status = "budget_exceeded";
      break;
    case "STDOUT_WRITE":
      s.stdout += p.text ?? "";
      break;
    case "STDERR_WRITE":
      s.stderr += p.text ?? "";
      break;
    case "VARIABLE_CREATED":
      bind(s, targetFrame(s, ev), p.name, p.value);
      break;
    case "VARIABLE_WRITTEN": {
      const frame = targetFrame(s, ev);
      if (!(p.name in frame.locals)) {
        (ev.meta ??= {})._undo_unbind = true;
      }
      bind(s, frame, p.name, p.new);
      break;
    }
    case "VARIABLE_DELETED": {
      const frame = targetFrame(s, ev);
      if (!(p.name in frame.locals)) (ev.meta ??= {})._undo_absent = true;
      unbind(s, frame, p.name);
      break;
    }
    case "SUBSCRIPT_WRITTEN":
      setIndex(s, p.container_ref, p.index, p.new, !(p.existed ?? true));
      break;
    case "SUBSCRIPT_DELETED":
      deleteIndex(s, p.container_ref, p.index);
      break;
    case "ATTRIBUTE_WRITTEN": {
      const rec = heapCopy(s, p.object_ref);
      if (rec) {
        rec.fields = { ...(rec.fields ?? {}), [p.name]: p.new };
        rec.n = Object.keys(rec.fields).length;
        s.heap[p.object_ref] = rec;
      }
      break;
    }
    case "OBJECT_CREATED":
      s.heap[p.ref] = p.snapshot ?? { ref: p.ref, t: p.kind };
      break;
    case "OBJECT_MUTATED":
      if (p.after) s.heap[p.ref] = p.after;
      break;
    case "OBJECT_FREED":
      delete s.heap[p.ref];
      break;
    case "FUNCTION_ENTERED": {
      const args = (p.args ?? {}) as Record<string, EncodedValue>;
      const frame: Frame = {
        frame_id: ev.frame, func_id: p.func_id ?? "", name: p.name ?? "?",
        depth: ev.depth, call_line: p.call_line ?? 0, line: ev.loc?.line ?? 0,
        args: Object.keys(args), locals: { ...args }, return_value: null,
        active: true, parent: p.caller_frame ?? -1, exit_reason: "",
      };
      s.frames.push(frame);
      s.call_tree.push({
        frame_id: frame.frame_id, parent: frame.parent, name: frame.name,
        func_id: frame.func_id, depth: frame.depth, call_line: frame.call_line,
        enter_step: ev.id, args: { ...args }, return_value: null,
        exit_step: -1, exit_reason: "",
      });
      break;
    }
    case "FUNCTION_RETURNED": {
      const top = s.frames[s.frames.length - 1];
      s.frames[s.frames.length - 1] = { ...top, return_value: p.value };
      updateCall(s, top.frame_id, { return_value: p.value });
      break;
    }
    case "FUNCTION_EXITED": {
      if (s.frames.length <= 1) break;
      const frame = s.frames.pop()!;
      const retired = { ...frame, active: false, exit_reason: p.reason ?? "return" };
      s.retired[frame.frame_id] = retired;
      updateCall(s, frame.frame_id, { exit_step: ev.id, exit_reason: retired.exit_reason });
      break;
    }
    case "LOOP_STARTED": {
      const lid = p.loop_id as string;
      if (s.loops[lid]) (ev.meta ??= {})._undo_loop = { ...s.loops[lid] };
      s.loops[lid] = {
        loop_id: lid, kind: p.kind ?? "for", line: ev.loc?.line ?? 0,
        iteration: -1, finished: false, exit: "",
      };
      break;
    }
    case "LOOP_ITERATION": {
      const loop = s.loops[p.loop_id];
      if (loop) s.loops[p.loop_id] = { ...loop, iteration: p.iteration ?? loop.iteration + 1 };
      break;
    }
    case "LOOP_FINISHED": {
      const loop = s.loops[p.loop_id];
      if (loop) s.loops[p.loop_id] = { ...loop, finished: true, exit: p.exit ?? "normal" };
      break;
    }
    case "EXCEPTION_RAISED":
      s.exception = {
        exc_type: p.exc_type ?? "Exception", message: p.message ?? "",
        line: ev.loc?.line ?? 0, handled: false,
      };
      break;
    case "EXCEPTION_HANDLED":
      if (s.exception) s.exception = { ...s.exception, handled: true };
      break;
    case "ALGORITHM_EVENT":
      forwardAlgorithm(s, ev);
      break;
    default:
      break; // unknown types are a no-op: forward compatibility, rule C5
  }
}

function forwardAlgorithm(s: ExecutionState, ev: AsEvent): void {
  const name = ev.payload.name as string;
  const key = `algo.${name}`;
  s.counters[key] = (s.counters[key] ?? 0) + 1;
  const args = (ev.payload.args ?? {}) as Record<string, any>;
  if (name === "metric") {
    const mkey = String(args.name ?? "metric");
    s.counters[mkey] = (s.counters[mkey] ?? 0) + Number(args.delta ?? 1);
    return;
  }
  if (!ANNOTATION_KINDS.has(name)) return;
  const annotation: Annotation = {
    event_id: ev.id, step: ev.id, kind: name,
    target_ref: ev.payload.ref ?? null,
    label: String(args.label ?? args.text ?? name),
    color: String(args.color ?? ""),
    index: intOrNull(args.index ?? args.i),
    lo: intOrNull(args.lo), hi: intOrNull(args.hi),
    value: args, ttl: ANNOTATION_TTL[name] ?? INFINITE_TTL,
    subject: annotationSubject(name, args),
  };
  s.annotations[ev.id] = annotation;
}

function inverse(s: ExecutionState, ev: AsEvent): void {
  const p = ev.payload;
  switch (ev.type) {
    case "PROGRAM_FINISHED":
      s.status = "running";
      s.finished_reason = "";
      break;
    case "BUDGET_EXCEEDED":
      s.status = "running";
      break;
    case "STDOUT_WRITE":
      if (p.text && s.stdout.endsWith(p.text)) s.stdout = s.stdout.slice(0, -p.text.length);
      break;
    case "STDERR_WRITE":
      if (p.text && s.stderr.endsWith(p.text)) s.stderr = s.stderr.slice(0, -p.text.length);
      break;
    case "VARIABLE_CREATED":
      unbind(s, targetFrame(s, ev), p.name);
      break;
    case "VARIABLE_WRITTEN": {
      const frame = targetFrame(s, ev);
      if (ev.meta?._undo_unbind) unbind(s, frame, p.name);
      else bind(s, frame, p.name, p.old);
      break;
    }
    case "VARIABLE_DELETED":
      if (!ev.meta?._undo_absent) bind(s, targetFrame(s, ev), p.name, p.old);
      break;
    case "SUBSCRIPT_WRITTEN":
      if (p.existed ?? true) setIndex(s, p.container_ref, p.index, p.old);
      else deleteIndex(s, p.container_ref, p.index);
      break;
    case "SUBSCRIPT_DELETED":
      setIndex(s, p.container_ref, p.index, p.old, true, p.position ?? null);
      break;
    case "ATTRIBUTE_WRITTEN": {
      const rec = heapCopy(s, p.object_ref);
      if (rec) {
        const fields = { ...(rec.fields ?? {}) };
        if (p.existed ?? true) fields[p.name] = p.old;
        else delete fields[p.name];
        rec.fields = fields;
        rec.n = Object.keys(fields).length;
        s.heap[p.object_ref] = rec;
      }
      break;
    }
    case "OBJECT_CREATED":
      delete s.heap[p.ref];
      break;
    case "OBJECT_MUTATED":
      if (p.before) s.heap[p.ref] = p.before;
      break;
    case "OBJECT_FREED":
      if (p.snapshot) s.heap[p.ref] = p.snapshot;
      break;
    case "FUNCTION_ENTERED":
      if (s.frames.length > 1) s.frames.pop();
      if (s.call_tree.length && s.call_tree[s.call_tree.length - 1].enter_step === ev.id) {
        s.call_tree.pop();
      }
      break;
    case "FUNCTION_RETURNED": {
      const top = s.frames[s.frames.length - 1];
      s.frames[s.frames.length - 1] = { ...top, return_value: null };
      updateCall(s, top.frame_id, { return_value: null });
      break;
    }
    case "FUNCTION_EXITED": {
      const frame = s.retired[ev.frame];
      if (!frame) break;
      delete s.retired[ev.frame];
      s.frames.push({ ...frame, active: true, exit_reason: "" });
      updateCall(s, ev.frame, { exit_step: -1, exit_reason: "" });
      break;
    }
    case "LOOP_STARTED": {
      const previous = ev.meta?._undo_loop as LoopState | undefined;
      if (previous) s.loops[p.loop_id] = { ...previous };
      else delete s.loops[p.loop_id];
      break;
    }
    case "LOOP_ITERATION": {
      const loop = s.loops[p.loop_id];
      if (loop) s.loops[p.loop_id] = { ...loop, iteration: (p.iteration ?? 0) - 1 };
      break;
    }
    case "LOOP_FINISHED": {
      const loop = s.loops[p.loop_id];
      if (loop) s.loops[p.loop_id] = { ...loop, finished: false, exit: "" };
      break;
    }
    case "EXCEPTION_RAISED":
      s.exception = null;
      break;
    case "EXCEPTION_HANDLED":
      if (s.exception) s.exception = { ...s.exception, handled: false };
      break;
    case "ALGORITHM_EVENT": {
      const name = ev.payload.name as string;
      const key = `algo.${name}`;
      if (s.counters[key]) {
        s.counters[key] -= 1;
        if (s.counters[key] <= 0) delete s.counters[key];
      }
      if (name === "metric") {
        const args = (ev.payload.args ?? {}) as Record<string, any>;
        const mkey = String(args.name ?? "metric");
        if (s.counters[mkey]) {
          s.counters[mkey] -= Number(args.delta ?? 1);
          if (s.counters[mkey] <= 0) delete s.counters[mkey];
        }
      }
      delete s.annotations[ev.id];
      break;
    }
    default:
      break;
  }
}

function intOrNull(v: any): number | null {
  if (typeof v === "boolean") return null;
  if (typeof v === "number") return v;
  if (v && typeof v === "object" && v.k === "int") return v.v;
  return null;
}

/** The visible annotation set: newest per key, expired ones dropped. */
export function liveAnnotations(s: ExecutionState): Annotation[] {
  const best = new Map<string, Annotation>();
  const cancelled = new Map<string, number>();
  for (const ann of Object.values(s.annotations)) {
    if (s.step - ann.step > ann.ttl) continue;
    if (ann.kind === "unmark") {
      const slot = `${ann.target_ref}|${ann.subject ?? ""}`;
      cancelled.set(slot, Math.max(cancelled.get(slot) ?? -1, ann.step));
      continue;
    }
    const key = `${ann.kind}|${ann.label}|${ann.target_ref}|${ann.subject ?? ""}`;
    const current = best.get(key);
    if (!current || ann.step > current.step) best.set(key, ann);
  }
  return [...best.values()]
    .filter((a) => {
      if (a.kind !== "mark") return true;
      const slot = `${a.target_ref}|${a.subject ?? ""}`;
      return (cancelled.get(slot) ?? -1) <= a.step;
    })
    .sort((a, b) => a.step - b.step);
}

/** Friendly names for heap objects, derived from live bindings. */
export function refNames(s: ExecutionState): Record<string, string> {
  const names: Record<string, string> = {};
  // Active frames first, then retired oldest-first, first-write-wins. Mirrors
  // ExecutionState.ref_names: last-write-wins let a recursive helper's `node`
  // parameter rename every object it touched.
  const retired = Object.keys(s.retired)
    .map(Number)
    .sort((a, b) => a - b)
    .map((k) => s.retired[k]);
  for (const frame of [...s.frames, ...retired]) {
    for (const [name, value] of Object.entries(frame.locals)) {
      if (UNINFORMATIVE_NAMES.has(name)) continue;
      const ref = value && (value as any).k === "ref" ? (value as any).r : null;
      if (ref && !(ref in names)) names[ref] = name;
    }
  }
  return names;
}
