/**
 * Client-side time travel: checkpoints plus invertible events.
 *
 * Mirror of backend/algostudio/state/timeline.py. Because the client holds the
 * events, every debugger control -- step, seek, play, step over/into/out, run
 * to breakpoint -- is a local computation. No debug protocol, no stopped/running
 * state machine, and stepping backwards works out of a function that already
 * returned.
 */

import type { AsEvent, ExecutionState } from "../api/types";
import { apply, cloneState, initialState, unapply } from "./reducer";

const DEFAULT_INTERVAL = 64;
const MAX_CHECKPOINTS = 512;

export class Timeline {
  readonly events: AsEvent[];
  readonly interval: number;
  private checkpoints = new Map<number, ExecutionState>();
  private built = false;

  constructor(events: AsEvent[], interval = DEFAULT_INTERVAL) {
    this.events = events;
    let step = interval;
    if (events.length / Math.max(step, 1) > MAX_CHECKPOINTS) {
      step = Math.max(step, Math.floor(events.length / MAX_CHECKPOINTS) + 1);
    }
    this.interval = Math.max(1, step);
  }

  get length(): number {
    return this.events.length;
  }

  get lastStep(): number {
    return this.events.length - 1;
  }

  private build(): void {
    if (this.built) return;
    const state = initialState();
    this.checkpoints.set(-1, cloneState(state));
    this.events.forEach((ev, i) => {
      apply(state, ev);
      if (i % this.interval === 0) this.checkpoints.set(i, cloneState(state));
    });
    this.checkpoints.set(this.lastStep, cloneState(state));
    this.built = true;
  }

  private nearest(step: number): [number, ExecutionState] {
    this.build();
    let index = Math.floor(step / this.interval) * this.interval;
    while (index >= 0 && !this.checkpoints.has(index)) index -= this.interval;
    if (index < 0 || index > step) return [-1, this.checkpoints.get(-1)!];
    return [index, this.checkpoints.get(index)!];
  }

  stateAt(step: number): ExecutionState {
    const target = Math.max(-1, Math.min(step, this.lastStep));
    if (target < 0) return initialState();
    const [base, snapshot] = this.nearest(target);
    const state = cloneState(snapshot);
    for (let i = base + 1; i <= target; i++) apply(state, this.events[i]);
    return state;
  }

  stepForward(state: ExecutionState): ExecutionState {
    const next = state.step + 1;
    if (next > this.lastStep) return state;
    return apply(state, this.events[next]);
  }

  /** O(1): apply the inverse of the event that produced this state. */
  stepBack(state: ExecutionState): ExecutionState {
    const current = state.step;
    if (current < 0) return state;
    return unapply(state, this.events[current], current >= 1 ? this.events[current - 1] : null);
  }

  seek(state: ExecutionState, target: number): ExecutionState {
    const goal = Math.max(-1, Math.min(target, this.lastStep));
    const current = state.step;
    if (goal === current) return state;
    if (goal > current) {
      for (let i = current + 1; i <= goal; i++) apply(state, this.events[i]);
      return state;
    }
    const backwardCost = current - goal;
    const [checkpoint] = this.nearest(goal);
    if (backwardCost <= goal - checkpoint) {
      let s = state;
      for (let i = 0; i < backwardCost; i++) s = this.stepBack(s);
      return s;
    }
    return this.stateAt(goal);
  }

  // ---- debugger navigation, all of it a search over the recording ----------
  nextMatching(step: number, predicate: (ev: AsEvent) => boolean, direction = 1): number | null {
    let i = step + direction;
    while (i >= 0 && i <= this.lastStep) {
      if (predicate(this.events[i])) return i;
      i += direction;
    }
    return null;
  }

  stepOver(step: number): number | null {
    const depth = this.events[step]?.depth ?? 0;
    return this.nextMatching(step, (e) => e.type === "LINE_EXECUTED" && e.depth <= depth);
  }

  stepInto(step: number): number | null {
    return this.nextMatching(step, (e) => e.type === "FUNCTION_ENTERED");
  }

  stepOut(step: number): number | null {
    const frame = this.events[step]?.frame;
    if (frame === undefined) return null;
    return this.nextMatching(step, (e) => e.type === "FUNCTION_EXITED" && e.frame === frame);
  }

  runToLine(step: number, lines: Set<number>, direction = 1): number | null {
    return this.nextMatching(
      step,
      (e) => e.type === "LINE_EXECUTED" && !!e.loc && lines.has(e.loc.line),
      direction,
    );
  }

  previousWrite(step: number, name: string): number | null {
    return this.nextMatching(
      step + 1,
      (e) =>
        (e.type === "VARIABLE_WRITTEN" || e.type === "VARIABLE_CREATED") &&
        e.payload.name === name,
      -1,
    );
  }
}
