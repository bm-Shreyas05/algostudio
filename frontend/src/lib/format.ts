import type { AsEvent, EncodedValue, HeapObject } from "../api/types";

/** Encoder tags whose `n` is a length. For an "object" it counts fields. */
const CONTAINERS = new Set([
  "list", "tuple", "set", "frozenset", "dict", "deque",
  "defaultdict", "OrderedDict", "Counter", "array",
]);

/** Compact rendering of an encoded value. Mirrors core/events.py::preview. */
export function preview(value: EncodedValue | undefined | null, max = 40): string {
  if (!value) return "?";
  switch (value.k) {
    case "none":
      return "None";
    case "int":
    case "float":
      // inf/nan are not valid JSON; the encoder parks them in `special`.
      return value.v === null ? String((value as any).special ?? "?") : String(value.v);
    case "bool":
      return value.v ? "True" : "False";
    case "str": {
      const body = value.v.length <= max ? value.v : value.v.slice(0, max - 1) + "…";
      return JSON.stringify(body);
    }
    case "ref":
      // "object[3]" read as a collection of three things; the 3 was the
      // number of fields. Without the heap there is no class name to give.
      return CONTAINERS.has(value.t) ? `${value.t}[${value.n}]` : value.t;
    case "cycle":
      return `↺ ${value.r}`;
    case "opaque":
      return value.repr.slice(0, max);
    default:
      return String(value);
  }
}

export function isRef(value: EncodedValue | undefined): value is Extract<EncodedValue, { k: "ref" }> {
  return !!value && (value as any).k === "ref";
}

/**
 * Like `preview`, but resolves a container's *current* size from the heap.
 *
 * The `n` carried on a ref is whatever the length was when the encoder first
 * saw the object -- containers are not re-encoded on every read, which is what
 * keeps a subscript read O(1) instead of O(len). So a panel that wants the live
 * length has to look it up.
 */
export function previewLive(
  value: EncodedValue | undefined,
  heap: Record<string, HeapObject>,
  max = 34,
): string {
  if (!isRef(value)) return preview(value, max);
  const record = heap[value.r];
  if (!record) return preview(value, max);
  // An instance of the program's own class is named by its class: `Node`.
  if (!CONTAINERS.has(record.t)) return record.cls ?? record.t;
  const size = record.n ?? record.items?.length ?? 0;
  return `${record.t}[${size}]`;
}

/**
 * A value as Python would print it -- `[1, 2, 3, 5, 7, 9]`, not `list[6]` --
 * cut to fit `max` characters.
 *
 * The variables panel used to show every list as its type and length, so the
 * one thing a learner is watching -- what is in the list now -- was hidden
 * behind a hover tooltip. As many items as fit are shown, then how many more
 * there are. One level of nesting is expanded (a small matrix reads as a
 * matrix); deeper than that, or when it will not fit, a container falls back
 * to its type and length, and an object to its class name.
 */
export function previewContents(
  value: EncodedValue | undefined,
  heap: Record<string, HeapObject>,
  max = 48,
): string {
  if (!isRef(value)) return preview(value, max);
  return contents(value, heap, max, 0) ?? previewLive(value, heap, max);
}

/** The printed form if anything useful fits in `max` characters, else null. */
function contents(
  value: Extract<EncodedValue, { k: "ref" }>,
  heap: Record<string, HeapObject>,
  max: number,
  depth: number,
): string | null {
  const record = heap[value.r];
  if (!record) return null;

  const inner = (v: EncodedValue): string => {
    if (!isRef(v)) return preview(v, 16);
    // A nested list is expanded once (a small matrix reads as a matrix). A
    // nested object is only named: `Node(value=8, left=Node, right=Node)`
    // says more than a line of cut-off field lists.
    const nested = heap[v.r];
    if (depth < 1 && nested && CONTAINERS.has(nested.t)) {
      const text = contents(v, heap, 24, depth + 1);
      if (text) return text;
    }
    return previewLive(v, heap);
  };

  let open = "[";
  let close = "]";
  let parts: string[];
  if (record.items) {
    if (record.t === "tuple") [open, close] = ["(", ")"];
    else if (record.t === "set" || record.t === "frozenset") [open, close] = ["{", "}"];
    else if (record.t === "deque") [open, close] = ["deque([", "])"];
    parts = record.items.map(inner);
  } else if (record.entries) {
    [open, close] = ["{", "}"];
    parts = record.entries.map(([k, v]) => `${inner(k)}: ${inner(v)}`);
  } else if (record.fields) {
    [open, close] = [`${record.cls ?? record.t}(`, ")"];
    parts = Object.entries(record.fields).map(([k, v]) => `${k}=${inner(v)}`);
  } else {
    return null;
  }

  const total = record.items || record.entries ? (record.n ?? parts.length) : parts.length;
  if (total === 0) return record.t === "set" ? "set()" : `${open}${close}`;
  for (let count = parts.length; count >= 1; count--) {
    const more = count < total ? `, … +${total - count}` : "";
    const text = `${open}${parts.slice(0, count).join(", ")}${more}${close}`;
    if (text.length <= max) return text;
  }
  return null;
}

export function scalarOf(value: EncodedValue | undefined): number | string | boolean | null {
  if (!value) return null;
  if (value.k === "int" || value.k === "float") {
    // inf / nan travel in `special`; returning null for them made numeric
    // comparisons in the views silently skip infinite distances.
    if (value.v === null && (value as any).special) {
      const parsed = Number((value as any).special);
      return Number.isNaN(parsed) ? null : parsed;
    }
    return value.v;
  }
  if (value.k === "str") return value.v;
  if (value.k === "bool") return value.v;
  return null;
}

export function renderHeap(record: HeapObject | undefined, limit = 12): string {
  if (!record) return "?";
  if (record.items) {
    const items = record.items.slice(0, limit).map((v) => preview(v, 14));
    const more = (record.n ?? 0) > limit ? `, …${record.n}` : "";
    return `[${items.join(", ")}${more}]`;
  }
  if (record.entries) {
    const pairs = record.entries
      .slice(0, limit)
      .map(([k, v]) => `${preview(k, 10)}: ${preview(v, 12)}`);
    const more = (record.n ?? 0) > limit ? `, …${record.n}` : "";
    return `{${pairs.join(", ")}${more}}`;
  }
  if (record.fields) {
    const fields = Object.entries(record.fields)
      .slice(0, limit)
      .map(([k, v]) => `${k}=${preview(v, 12)}`);
    return `${record.cls}(${fields.join(", ")})`;
  }
  return record.t;
}

/** One-line human description of an event. Mirrors core/events.py::summarize. */
export function summarize(ev: AsEvent): string {
  const p = ev.payload;
  switch (ev.type) {
    case "LINE_EXECUTED":
      return `line ${ev.loc?.line ?? "?"}`;
    case "VARIABLE_CREATED":
      return `${p.name} = ${preview(p.value)}`;
    case "VARIABLE_WRITTEN":
      return `${p.name}: ${preview(p.old)} → ${preview(p.new)}`;
    case "VARIABLE_READ":
      return `read ${p.name} = ${preview(p.value)}`;
    case "VARIABLE_DELETED":
      return `del ${p.name}`;
    case "SUBSCRIPT_READ":
      return `${p.container_name ?? p.container_ref}[${p.index}] → ${preview(p.value)}`;
    case "SUBSCRIPT_WRITTEN":
      return `${p.container_name ?? p.container_ref}[${p.index}]: ${preview(p.old)} → ${preview(p.new)}`;
    case "SUBSCRIPT_DELETED":
      return `del ${p.container_name ?? p.container_ref}[${p.index}]`;
    case "ATTRIBUTE_WRITTEN":
      return `.${p.name}: ${preview(p.old)} → ${preview(p.new)}`;
    case "CONDITION_EVALUATED":
      return `${p.expr} → ${p.result}`;
    case "BRANCH_TAKEN":
      return `branch: ${p.branch}`;
    case "LOOP_STARTED":
      return `${p.kind} loop starts`;
    case "LOOP_ITERATION":
      return p.var
        ? `iteration ${p.iteration} (${p.var} = ${preview(p.value)})`
        : `iteration ${p.iteration}`;
    case "LOOP_FINISHED": {
      const passes = `${p.iterations} ${p.iterations === 1 ? "pass" : "passes"}`;
      return p.exit && p.exit !== "normal"
        ? `loop ends after ${passes} (${p.exit})`
        : `loop ends after ${passes}`;
    }
    case "FUNCTION_ENTERED": {
      const args = Object.entries((p.args ?? {}) as Record<string, EncodedValue>)
        .map(([k, v]) => `${k}=${preview(v, 16)}`)
        .join(", ");
      return `call ${p.name}(${args})`;
    }
    case "FUNCTION_RETURNED":
      return `return ${preview(p.value)}`;
    case "FUNCTION_EXITED":
      // "(return)" on every exit was the engine talking to itself; only an
      // unusual way out -- an exception -- is worth saying.
      return p.reason && p.reason !== "return"
        ? `leave ${p.name ?? ""}() (${p.reason})`
        : `leave ${p.name ?? ""}()`;
    case "EXPRESSION_EVALUATED": {
      const ops = (p.operands ?? []) as EncodedValue[];
      if (p.op && ops.length === 2) {
        return `${preview(ops[0], 16)} ${p.op} ${preview(ops[1], 16)} = ${preview(p.value, 16)}`;
      }
      return `${p.expr ?? "expr"} = ${preview(p.value)}`;
    }
    case "OBJECT_MUTATED":
      return `${p.name ?? p.ref}.${p.op}(…)`;
    case "OBJECT_CREATED":
      // Not the heap id ("h7"), which names nothing the reader can see.
      return `new ${p.kind}`;
    case "STDOUT_WRITE":
      return "print " + String(p.text ?? "").replace(/\n+$/, "").slice(0, 60);
    case "EXCEPTION_RAISED":
      return `${p.exc_type}: ${p.message}`;
    case "EXCEPTION_HANDLED":
      return `handled ${p.exc_type}`;
    case "PROGRAM_STARTED":
      return "program started";
    case "PROGRAM_FINISHED":
      return p.status === "ok" ? "program finished" : `program stopped (${String(p.status).replace(/_/g, " ")})`;
    case "BUDGET_EXCEEDED":
      return `stopped: ${p.reason}`;
    case "INSTRUMENTATION_SKIPPED":
      return `reduced detail: ${p.reason}`;
    case "ALGORITHM_EVENT":
      return summarizeAlgorithm(p);
    default:
      return ev.type.toLowerCase().replace(/_/g, " ");
  }
}

function summarizeAlgorithm(p: Record<string, any>): string {
  const a = (p.args ?? {}) as Record<string, any>;
  switch (p.name) {
    case "swap":
      return `swap [${a.i}] ↔ [${a.j}]`;
    case "compare": {
      const where =
        a.i !== null && a.i !== undefined && a.j !== null && a.j !== undefined
          ? ` [${a.i}] vs [${a.j}]`
          : a.i !== null && a.i !== undefined
            ? ` [${a.i}]`
            : "";
      return `compare${where} ${preview(a.a, 14)} ${a.op ?? "vs"} ${preview(a.b, 14)} → ${a.result}`;
    }
    case "visit":
      return `visit ${preview(a.node, 16)}`;
    case "relax":
      return `relax → ${a.v ?? preview(a.v)}${a.improved ? " (improved)" : ""}`;
    case "pointer":
      return `pointer ${a.label} → [${a.index}]`;
    case "region":
      return `region ${a.label} [${a.lo}..${a.hi}]`;
    case "enqueue":
    case "push":
      return `${p.name} ${preview(a.value, 16)}`;
    case "dequeue":
    case "pop":
      return `${p.name} → ${preview(a.value, 16)}`;
    case "note":
      return String(a.text ?? "");
    case "metric":
      return `metric ${a.name} +${a.delta ?? 1}`;
    case "result":
      return `result = ${preview(a.value, 24)}`;
    default:
      return String(p.name);
  }
}

export const CATEGORY: Record<string, string> = {
  PROGRAM_STARTED: "lifecycle", PROGRAM_FINISHED: "lifecycle",
  BUDGET_EXCEEDED: "lifecycle", INSTRUMENTATION_SKIPPED: "lifecycle",
  STDOUT_WRITE: "io", STDERR_WRITE: "io", STDIN_READ: "io",
  LINE_EXECUTED: "flow", CONDITION_EVALUATED: "flow", BRANCH_TAKEN: "flow",
  LOOP_STARTED: "loop", LOOP_ITERATION: "loop", LOOP_FINISHED: "loop",
  FUNCTION_ENTERED: "call", FUNCTION_RETURNED: "call", FUNCTION_EXITED: "call",
  EXCEPTION_RAISED: "error", EXCEPTION_HANDLED: "error",
  VARIABLE_CREATED: "data", VARIABLE_WRITTEN: "data", VARIABLE_DELETED: "data",
  SUBSCRIPT_WRITTEN: "data", SUBSCRIPT_DELETED: "data", ATTRIBUTE_WRITTEN: "data",
  VARIABLE_READ: "read", SUBSCRIPT_READ: "read", ATTRIBUTE_READ: "read",
  OBJECT_CREATED: "heap", OBJECT_MUTATED: "heap", OBJECT_FREED: "heap",
  EXPRESSION_EVALUATED: "expr", ALGORITHM_EVENT: "algorithm",
  STACK_PUSH: "structure", STACK_POP: "structure",
  QUEUE_ENQUEUE: "structure", QUEUE_DEQUEUE: "structure",
};

export const CATEGORY_ORDER = [
  "algorithm", "data", "call", "flow", "loop", "heap", "io", "error",
  "expr", "read", "structure", "lifecycle",
];

export function categoryOf(ev: AsEvent): string {
  return CATEGORY[ev.type] ?? "other";
}

export function formatMetric(key: string): string {
  return key.replace(/_/g, " ").replace(/\balgo\./, "");
}
