import { useMemo } from "react";
import type { AsEvent, ExecutionState } from "../api/types";
import { preview, scalarOf } from "../lib/format";

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
  const focus = useMemo(() => describe(events, step), [events, step]);

  const counters = useMemo(() => {
    const wanted = [
      ["comparisons", "compares"], ["swaps", "swaps"], ["algo.visit", "visited"],
      ["algo.relax", "relaxed"], ["array_writes", "writes"],
      ["function_calls", "calls"], ["loop_iterations", "iterations"],
    ] as const;
    return wanted
      .map(([key, label]) => [label, state.counters[key]] as const)
      .filter(([, value]) => typeof value === "number" && value > 0);
  }, [state.counters]);

  const frame = state.frames[state.frames.length - 1];

  return (
    <div className={`focus-strip tone-${focus.tone}`}>
      <div className="focus-main">
        <span className="focus-headline">{focus.headline}</span>
        {focus.detail && <span className="focus-detail">{focus.detail}</span>}
      </div>
      <div className="focus-meta">
        {statement && <code className="focus-stmt">{statement}</code>}
        {frame && frame.name !== "<module>" && (
          <span className="focus-frame">in {frame.name}()</span>
        )}
        {state.frames.length > 2 && (
          <span className="focus-frame">depth {state.frames.length - 1}</span>
        )}
      </div>
      {counters.length > 0 && (
        <div className="focus-counters">
          {counters.map(([label, value]) => (
            <span key={label}>
              <b>{value}</b> {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
function describe(events: AsEvent[], step: number): Focus {
  if (step < 0 || !events.length) {
    return { tone: "idle", headline: "Ready" };
  }
  const low = Math.max(0, step - WINDOW);
  let best: { rank: number; focus: Focus } | null = null;

  for (let i = step; i >= low; i--) {
    const candidate = rank(events[i]);
    if (candidate && (!best || candidate.rank > best.rank)) best = candidate;
    // An operation right on the cursor always wins; no need to look further.
    if (best && best.rank >= 90 && i === step) break;
  }
  return best?.focus ?? { tone: "idle", headline: `Line ${events[step]?.loc?.line ?? "?"}` };
}

function rank(ev: AsEvent | undefined): { rank: number; focus: Focus } | null {
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
    const where = p.ref ? "" : "";
    switch (name) {
      case "swap":
        return { rank: 95, focus: {
          tone: "algorithm",
          headline: `Swap [${a.i}] ↔ [${a.j}]`,
          detail: `${preview(a.b, 14)} and ${preview(a.a, 14)} exchange places${where}`,
        } };
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
        .map(([k, v]) => `${k}=${preview(v, 10)}`)
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
      return { rank: 99, focus: {
        tone: p.status === "ok" ? "idle" : "error",
        headline: p.status === "ok" ? "Finished" : `Stopped: ${p.status}`,
      } };
    default:
      return null;
  }
}
