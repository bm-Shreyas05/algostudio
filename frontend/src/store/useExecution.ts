import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  Analytics, AsEvent, ExecutionState, ExecutionSummary, ViewDescriptor,
} from "../api/types";
import {
  getBrowserEngine, type EngineStatus,
} from "../engine/browserEngine";
import { initialState } from "../engine/reducer";
import { Timeline } from "../engine/timeline";

export interface ExecutionBundle {
  summary: ExecutionSummary;
  events: AsEvent[];
  analytics: Analytics;
  views: ViewDescriptor[];
}

export interface Transport {
  playing: boolean;
  speed: number;
}

/**
 * How far one "step" moves.
 *
 * Stepping one *event* at a time is faithful but unwatchable: a 440-event run
 * is mostly subscript reads and sub-expression results. Stepping by line is
 * what a debugger does and what people expect; stepping by operation follows
 * only the events that changed something.
 */
export type StepMode = "event" | "line" | "operation";

const OPERATION_TYPES = new Set([
  "VARIABLE_CREATED", "VARIABLE_WRITTEN", "VARIABLE_DELETED",
  "SUBSCRIPT_WRITTEN", "SUBSCRIPT_DELETED", "ATTRIBUTE_WRITTEN",
  "OBJECT_MUTATED", "ALGORITHM_EVENT", "FUNCTION_ENTERED",
  "FUNCTION_RETURNED", "STDOUT_WRITE", "EXCEPTION_RAISED",
]);

const MATCHERS: Record<StepMode, (ev: AsEvent) => boolean> = {
  event: () => true,
  line: (ev) => ev.type === "LINE_EXECUTED",
  operation: (ev) => OPERATION_TYPES.has(ev.type),
};

/**
 * Holds the recording and the cursor over it.
 *
 * All navigation is local: the client runs the same reducer as the server, so
 * step/seek/play never touch the network. That is what makes stepping backwards
 * feel instant, and it is why a dropped connection degrades to "no live
 * updates" rather than "the debugger is stuck".
 */
export function useExecution() {
  const [bundle, setBundle] = useState<ExecutionBundle | null>(null);
  const [state, setState] = useState<ExecutionState>(() => initialState());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>("");
  const [transport, setTransport] = useState<Transport>({ playing: false, speed: 8 });
  const [stepMode, setStepMode] = useState<StepMode>("line");
  const [breakpoints, setBreakpoints] = useState<Set<number>>(new Set());
  // Loading the in-browser engine takes seconds the first time. The UI has
  // to say what is happening, or a click on Run looks like a hang.
  const [engineStatus, setEngineStatus] = useState<EngineStatus | null>(null);

  const timelineRef = useRef<Timeline | null>(null);
  const stateRef = useRef<ExecutionState>(state);
  stateRef.current = state;

  const timeline = timelineRef.current;

  const publish = useCallback((next: ExecutionState) => {
    // The reducer mutates in place for speed; a new wrapper object is what
    // tells React the cursor moved.
    setState({ ...next });
  }, []);

  const load = useCallback(async (executionId: string) => {
    setBusy(true);
    setError("");
    try {
      const summary = await api.summary(executionId);
      const events = await api.allEvents(executionId, summary.event_count);
      const [analytics, views] = await Promise.all([
        api.analytics(executionId),
        api.views(executionId, Math.max(0, events.length - 1)),
      ]);
      const tl = new Timeline(events);
      timelineRef.current = tl;
      setBundle({ summary, events, analytics, views: views.plan });
      publish(tl.stateAt(0));
      // Start playing straight away. Clicking Run and being left staring at a
      // blank canvas -- because step 1 is before anything exists -- is the
      // single most confusing thing the UI did.
      setTransport((t) => ({ ...t, playing: tl.lastStep > 0 }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      timelineRef.current = null;
      setBundle(null);
    } finally {
      setBusy(false);
    }
  }, [publish]);

  const run = useCallback(async (source: string, granularity: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await api.run(source, { granularity });
      await load(result.execution_id);
      return result;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
      setBusy(false);
      return null;
    }
  }, [load]);

  /**
   * Run source the visitor wrote, in this tab.
   *
   * Deliberately a separate path from `run`, not a flag on it. The two differ
   * in where the code executes, which is the single most important thing about
   * this app's security posture — burying that in a boolean would make the
   * call sites read as though it did not matter.
   *
   * The result is assembled into the same ExecutionBundle the HTTP path
   * produces, so everything downstream — the reducer, the timeline, every view
   * — is unaware of which engine ran.
   */
  const runLocal = useCallback(
    async (source: string, granularity: string) => {
      setBusy(true);
      setError("");
      try {
        const engine = await getBrowserEngine(setEngineStatus);
        const result = engine.run(source, granularity);

        if (result.status === "unsupported") {
          setError(result.error?.message ?? "That program uses something unsupported.");
          setBusy(false);
          return null;
        }

        const tl = new Timeline(result.events);
        timelineRef.current = tl;
        setBundle({
          summary: {
            execution_id: "local",
            status: result.status,
            language: "python",
            algorithm_id: null,
            granularity,
            event_count: result.event_count,
            wall_ms: result.wall_ms,
            sandbox_mode: "browser",
            capability_report: result.capability_report,
            error: result.error,
            source,
            lifters: result.meta?.lifters ?? true,
          } as any,
          events: result.events,
          analytics: result.analytics,
          views: engine.views(Math.max(0, result.last_step)),
        });
        publish(tl.stateAt(0));
        setTransport((t) => ({ ...t, playing: tl.lastStep > 0 }));
        return result;
      } catch (e) {
        setError(
          e instanceof Error
            ? `The in-browser engine failed to start: ${e.message}`
            : String(e),
        );
        timelineRef.current = null;
        setBundle(null);
        return null;
      } finally {
        setBusy(false);
      }
    },
    [publish],
  );

  const runAlgorithm = useCallback(
    async (id: string, inputs: Record<string, any>, granularity: string) => {
      setBusy(true);
      setError("");
      try {
        const result = await api.runAlgorithm(id, inputs, { granularity });
        await load(result.execution_id);
        return result;
      } catch (e) {
        setError(e instanceof ApiError ? e.message : String(e));
        setBusy(false);
        return null;
      }
    },
    [load],
  );

  const seek = useCallback((step: number) => {
    const tl = timelineRef.current;
    if (!tl) return;
    publish(tl.seek(stateRef.current, step));
  }, [publish]);

  const stepForward = useCallback(() => {
    const tl = timelineRef.current;
    if (!tl) return;
    const current = stateRef.current.step;
    if (stepMode === "event") {
      publish(tl.stepForward(stateRef.current));
      return;
    }
    const target = tl.nextMatching(current, MATCHERS[stepMode], 1);
    // No further match means the run is over; land on the end rather than
    // freezing on a step that looks arbitrary.
    publish(tl.seek(stateRef.current, target ?? tl.lastStep));
  }, [publish, stepMode]);

  const stepBack = useCallback(() => {
    const tl = timelineRef.current;
    if (!tl) return;
    const current = stateRef.current.step;
    if (stepMode === "event") {
      publish(tl.stepBack(stateRef.current));
      return;
    }
    const target = tl.nextMatching(current, MATCHERS[stepMode], -1);
    publish(tl.seek(stateRef.current, target ?? 0));
  }, [publish, stepMode]);

  const jump = useCallback((finder: (tl: Timeline, step: number) => number | null) => {
    const tl = timelineRef.current;
    if (!tl) return;
    const target = finder(tl, stateRef.current.step);
    if (target !== null) seek(target);
  }, [seek]);

  const toggleBreakpoint = useCallback((line: number) => {
    setBreakpoints((current) => {
      const next = new Set(current);
      if (next.has(line)) next.delete(line);
      else next.add(line);
      return next;
    });
  }, []);

  const runToBreakpoint = useCallback((direction = 1) => {
    const tl = timelineRef.current;
    if (!tl || breakpoints.size === 0) return;
    const target = tl.runToLine(stateRef.current.step, breakpoints, direction);
    if (target !== null) seek(target);
  }, [breakpoints, seek]);

  // Playback is timer-driven, not requestAnimationFrame-driven.
  //
  // rAF is throttled to a crawl (and in some hosts stopped entirely) whenever
  // the page is not visible, so a user who switched tabs mid-playback came back
  // to a run that had silently stalled. Playback is a time-based process, not a
  // rendering one, so a timer is both the correct primitive and the robust one.
  useEffect(() => {
    if (!transport.playing || !timelineRef.current) return;
    let cancelled = false;
    let timer = 0;
    const interval = 1000 / Math.max(1, transport.speed);

    const tick = () => {
      if (cancelled) return;
      const tl = timelineRef.current;
      if (!tl) return;
      if (stateRef.current.step >= tl.lastStep) {
        setTransport((t) => ({ ...t, playing: false }));
        return;
      }
      const target =
        stepMode === "event"
          ? stateRef.current.step + 1
          : tl.nextMatching(stateRef.current.step, MATCHERS[stepMode], 1);
      publish(tl.seek(stateRef.current, target ?? tl.lastStep));
      timer = window.setTimeout(tick, interval);
    };

    timer = window.setTimeout(tick, interval);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [transport.playing, transport.speed, stepMode, publish]);

  const currentEvent = useMemo(
    () => (bundle && state.step >= 0 ? bundle.events[state.step] : null),
    [bundle, state.step],
  );

  const replay = useCallback(() => {
    seek(0);
    setTransport((t) => ({ ...t, playing: true }));
  }, [seek]);

  return {
    bundle, state, busy, error, transport, stepMode, breakpoints, timeline,
    currentEvent, setTransport, setStepMode, run, runLocal, runAlgorithm, load,
    seek, stepForward, stepBack, jump, toggleBreakpoint, runToBreakpoint,
    setError, replay, engineStatus,
  };
}
