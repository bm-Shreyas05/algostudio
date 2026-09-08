import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type {
  Analytics, AsEvent, ExecutionState, ExecutionSummary, ViewDescriptor,
} from "../api/types";
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
  const [transport, setTransport] = useState<Transport>({ playing: false, speed: 12 });
  const [breakpoints, setBreakpoints] = useState<Set<number>>(new Set());

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
      publish(tl.stateAt(Math.min(1, tl.lastStep)));
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
    publish(tl.stepForward(stateRef.current));
  }, [publish]);

  const stepBack = useCallback(() => {
    const tl = timelineRef.current;
    if (!tl) return;
    publish(tl.stepBack(stateRef.current));
  }, [publish]);

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

  // Playback: rAF-driven forward stepping, cancelled on pause or at the end.
  useEffect(() => {
    if (!transport.playing || !timelineRef.current) return;
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const tl = timelineRef.current;
      if (!tl) return;
      const interval = 1000 / Math.max(1, transport.speed);
      if (now - last >= interval) {
        last = now;
        if (stateRef.current.step >= tl.lastStep) {
          setTransport((t) => ({ ...t, playing: false }));
          return;
        }
        publish(tl.stepForward(stateRef.current));
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [transport.playing, transport.speed, publish]);

  const currentEvent = useMemo(
    () => (bundle && state.step >= 0 ? bundle.events[state.step] : null),
    [bundle, state.step],
  );

  return {
    bundle, state, busy, error, transport, breakpoints, timeline, currentEvent,
    setTransport, run, runAlgorithm, load, seek, stepForward, stepBack, jump,
    toggleBreakpoint, runToBreakpoint, setError,
  };
}
