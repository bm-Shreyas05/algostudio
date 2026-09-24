import { useMemo } from "react";
import type { AsEvent, EncodedValue, ExecutionState, HeapObject } from "../api/types";
import { preview, previewContents, previewLive, scalarOf } from "../lib/format";

/**
 * The headline: what the algorithm is doing at this exact step.
 *
 * Stepping by line means the cursor usually lands on a LINE_EXECUTED event
 * while the interesting operation -- the swap, the relaxation, the visit -- is
 * a few events further on. So this scans a small window around the cursor and
 * reports the most *significant* thing in it, rather than whatever the cursor
 * happens to be sitting on.
 *
 * Priority is by event kind, never by algorithm: an ALGORITHM_EVENT beats a
 * mutation, which beats a branch, which beats a bare line.
 */
interface Focus {
  tone: "algorithm" | "data" | "flow" | "call" | "error" | "idle";
  headline: string;
  detail?: string;
  /** The run's answer; printed from the heap, so a list shows its contents. */
  result?: EncodedValue;
}

const WINDOW = 6;

export function FocusStrip({
  state, events, step, statement,
}: {
  state: ExecutionState;
  events: AsEvent[];
  step: number;
  statement: string;
}) {
  const focus = useMemo(() => describe(events, step, state.heap), [events, step, state.heap]);
  // Once the program has ended, the line it last touched is history -- at the
  // end of a bubble sort that was `def bubble_sort(arr):`, which read as
  // though the sort were about to start again.
  const finished = Boolean(state.finished_reason);

  const counters = useMemo(() => {
    // Keys as the reducer counts them live. This list once asked for
    // "comparisons" and "swaps", which only exist in the whole-run totals, so
    // the two counters that matter most for a sort never appeared at all.
    const wanted = [
      ["algo.compare", "comparison", "comparisons"], ["algo.swap", "swap", "swaps"],
      ["algo.visit", "visited", "visited"], ["algo.relax", "relaxed", "relaxed"],
      ["array_writes", "item write", "item writes"],
      // "made", because "4 calls" beside "4 calls deep" read as one fact twice.
      ["function_calls", "call made", "calls made"],
      ["loop_iterations", "loop pass", "loop passes"],
    ] as const;
    // Two, not seven. Watching comparisons climb is how you see a quadratic
    // sort being quadratic, so the counters stay -- but a third row of seven
    // numbers under every step was noise, and the full set lives in Stats.
    return wanted
      .map(([key, one, many]) => {
        const value = state.counters[key];
        return [value === 1 ? one : many, value] as const;
      })
      .filter(([, value]) => typeof value === "number" && value > 0)
      .slice(0, 2);
  }, [state.counters]);

  const frame = state.frames[state.frames.length - 1];

  return (
    <div className={`focus-strip tone-${focus.tone}`}>
      <div className="focus-main">
        <span className="focus-headline">{focus.headline}</span>
        {focus.result ? (
          <span className="focus-detail">result: {previewContents(focus.result, state.heap, 60)}</span>
        ) : (
          focus.detail && <span className="focus-detail">{focus.detail}</span>
        )}
      </div>
      <div className="focus-meta">
        {statement && !finished && <code className="focus-stmt">{statement}</code>}
        {!finished && frame && frame.name !== "<module>" && (
          <span className="focus-frame">in {frame.name}()</span>
        )}
        {state.frames.length > 2 && (
          <span className="focus-frame">{state.frames.length - 1} calls deep</span>
        )}
        {counters.map(([label, value]) => (
          <span key={label} className="focus-count">
            <b>{value}</b> {label}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
function describe(events: AsEvent[], step: number, heap: Record<string, HeapObject>): Focus {
  if (step < 0 || !events.length) {
    return { tone: "idle", headline: "Ready" };
  }
  const low = Math.max(0, step - WINDOW);
  let best: { rank: number; focus: Focus } | null = null;

  for (let i = step; i >= low; i--) {
    const candidate = rank(events[i], heap);
    if (candidate && (!best || candidate.rank > best.rank)) best = candidate;
    // An operation right on the cursor always wins; no need to look further.
    if (best && best.rank >= 90 && i === step && events[i].type !== "PROGRAM_FINISHED") break;
  }
  return best?.focus ?? { tone: "idle", headline: `Line ${events[step]?.loc?.line ?? "?"}` };
}

function rank(
  ev: AsEvent | undefined,
  heap: Record<string, HeapObject>,
): { rank: number; focus: Focus } | null {
  if (!ev) return null;
  const p = ev.payload;

  if (ev.type === "EXCEPTION_RAISED") {
    return {
      rank: 100,
      focus: { tone: "error", headline: `${p.exc_type}`, detail: p.message },
    };
  }

  if (ev.type === "ALGORITHM_EVENT") {
    const a = (p.args ?? {}) as Record<string, any>;
    const name = p.name as string;
    switch (name) {
      case "swap":
        return { rank: 95, focus: {
          tone: "algorithm",
          headline: `Swap [${a.i}] ↔ [${a.j}]`,
          detail: `${preview(a.b, 14)} and ${preview(a.a, 14)} exchange places`,
        } };
      case "result":
        // What the catalogue's call returned: the answer the whole run was for.
        return { rank: 98, focus: { tone: "idle", headline: "Finished", result: a.value } };
      case "compare": {
        const lhs = a.i !== null && a.i !== undefined ? `[${a.i}]` : "";
        const rhs = a.j !== null && a.j !== undefined ? `[${a.j}]` : "";
        return { rank: 90, focus: {
          tone: "algorithm",
          headline: `Compare ${preview(a.a, 12)} ${a.op ?? "vs"} ${preview(a.b, 12)}`,
          detail: `${lhs}${lhs && rhs ? " against " : ""}${rhs} → ${a.result}`,
        } };
      }
      case "visit":
        return { rank: 96, focus: {
          tone: "algorithm",
          headline: `Visit ${preview(a.node, 16)}`,
          detail: "this node is now settled",
        } };
      case "discover":
        return { rank: 92, focus: {
          tone: "algorithm",
          headline: `Discover ${preview(a.node, 16)}`,
          detail: a.via ? `reached from ${preview(a.via, 12)}` : undefined,
        } };
      case "relax": {
        const improved = a.improved;
        return { rank: 94, focus: {
          tone: "algorithm",
          headline: `Relax ${scalarOf(a.u) ?? preview(a.u, 8)} → ${scalarOf(a.v) ?? preview(a.v, 8)}`,
          detail: improved
            ? `shorter route found (weight ${scalarOf(a.weight) ?? "?"})`
            : "no improvement — keeping the existing distance",
        } };
      }
      case "enqueue":
      case "push":
        return { rank: 88, focus: {
          tone: "algorithm",
          headline: `${name === "push" ? "Push" : "Enqueue"} ${preview(a.value, 16)}`,
          detail: `${a.length} waiting`,
        } };
      case "dequeue":
      case "pop":
        return { rank: 88, focus: {
          tone: "algorithm",
          headline: `${name === "pop" ? "Pop" : "Dequeue"} ${preview(a.value, 16)}`,
          detail: `${a.length} left`,
        } };
      case "pointer":
        return { rank: 70, focus: {
          tone: "algorithm",
          headline: `${a.label} → index ${a.index}`,
        } };
      case "region":
        return { rank: 68, focus: {
          tone: "algorithm",
          headline: `${a.label}: [${a.lo} … ${a.hi}]`,
          detail: `${Math.max(0, (a.hi ?? 0) - (a.lo ?? 0) + 1)} elements still in play`,
        } };
      case "note":
        return { rank: 72, focus: { tone: "algorithm", headline: String(a.text ?? "") } };
      default:
        return null;
    }
  }

  switch (ev.type) {
    case "SUBSCRIPT_WRITTEN":
      return { rank: 60, focus: {
        tone: "data",
        headline: `${p.container_name ?? "array"}[${p.index}] = ${preview(p.new, 16)}`,
        detail: p.old ? `was ${preview(p.old, 16)}` : undefined,
      } };
    case "OBJECT_MUTATED":
      return { rank: 58, focus: {
        tone: "data",
        headline: `${p.name ?? "object"}.${p.op}()`,
      } };
    case "VARIABLE_WRITTEN":
      return { rank: 52, focus: {
        tone: "data",
        headline: `${p.name} = ${preview(p.new, 18)}`,
        detail: `was ${preview(p.old, 18)}`,
      } };
    case "VARIABLE_CREATED":
      return { rank: 50, focus: {
        tone: "data",
        headline: `${p.name} = ${preview(p.value, 18)}`,
        detail: "first assignment",
      } };
    case "FUNCTION_ENTERED": {
      const args = Object.entries((p.args ?? {}) as Record<string, any>)
        .map(([k, v]) => `${k}=${previewLive(v, heap, 10)}`)
        .join(", ");
      return { rank: 66, focus: {
        tone: "call", headline: `Call ${p.name}(${args})`,
      } };
    }
    case "FUNCTION_RETURNED":
      return { rank: 64, focus: {
        tone: "call", headline: `Return ${preview(p.value, 20)}`,
      } };
    case "CONDITION_EVALUATED":
      return { rank: 44, focus: {
        tone: "flow",
        headline: `${p.expr} → ${p.result}`,
        detail: p.result ? "taking this branch" : "skipping this branch",
      } };
    case "LOOP_ITERATION":
      return { rank: 40, focus: {
        tone: "flow",
        headline: p.var
          ? `Iteration ${p.iteration} — ${p.var} = ${preview(p.value, 12)}`
          : `Iteration ${p.iteration}`,
      } };
    case "STDOUT_WRITE":
      return { rank: 42, focus: {
        tone: "flow", headline: `Prints ${JSON.stringify(String(p.text ?? "").trim())}`,
      } };
    case "PROGRAM_FINISHED":
      // Rank 97: below a "result" a step earlier, which says the same thing
      // and also what the answer was.
      return { rank: 97, focus: {
        tone: p.status === "ok" ? "idle" : "error",
        headline: p.status === "ok" ? "Finished" : stoppedBecause(p.status),
        detail: p.status === "ok" ? "step back to see any earlier moment" : undefined,
      } };
    default:
      return null;
  }
}

/** A run's end status, as a sentence rather than the engine's enum. */
export function stoppedBecause(status: string): string {
  switch (status) {
    case "budget_exceeded": return "Stopped: too many steps";
    case "timeout": return "Stopped: took too long";
    case "error": return "Ended with an error";
    default: return `Stopped (${status.replace(/_/g, " ")})`;
  }
}
