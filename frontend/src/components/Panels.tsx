import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Analytics, AsEvent, EncodedValue, ExecutionState, Frame,
} from "../api/types";
import {
  categoryOf, CATEGORY_ORDER, formatMetric, preview, previewLive, renderHeap, summarize,
} from "../lib/format";

/* ------------------------------------------------------------------ variables */
/** What the current step did to a binding, taken straight from the event. */
export type ChangedBinding =
  | { name: string; old: EncodedValue | null; created: boolean }
  | null;

export function VariablesPanel({
  state, changed, onInspect,
}: {
  state: ExecutionState;
  changed: ChangedBinding;
  onInspect: (name: string) => void;
}) {
  const frame = state.frames[state.frames.length - 1];
  const globals = state.frames[0]?.locals ?? {};
  const showGlobals = state.frames.length > 1;

  const row = (name: string, value: EncodedValue, scope: string) => {
    const hit = changed && changed.name === name;
    const wasWritten = Boolean(hit && !changed!.created);
    const wasCreated = Boolean(hit && changed!.created);
    const ref = (value as any)?.k === "ref" ? (value as any).r : null;
    return (
      <tr
        key={`${scope}-${name}`}
        className={wasWritten ? "changed" : wasCreated ? "created" : undefined}
      >
        <td className="k" onClick={() => onInspect(name)} title="show where this changed">
          {name}
        </td>
        <td className="v">
          {wasWritten && changed!.old && (
            <span className="old">{previewLive(changed!.old, state.heap, 18)} →</span>
          )}{" "}
          {previewLive(value, state.heap, 34)}
          {ref && (
            // Object identity, which is what makes aliasing visible: two
            // variables showing the same number are the same object. Shown as
            // "#8" rather than the internal "h8", and the tooltip says why it
            // is there at all.
            <span
              className="ref-badge"
              title={
                `Object #${ref.replace(/^h/, "")} — any variable showing the same ` +
                `number refers to this same object.\n\n${renderHeap(state.heap[ref])}`
              }
            >
              #{ref.replace(/^h/, "")}
            </span>
          )}
        </td>
      </tr>
    );
  };

  return (
    <div className="panel-body variables">
      <table>
        <tbody>
          {Object.entries(frame?.locals ?? {}).map(([n, v]) => row(n, v, "local"))}
          {showGlobals && Object.keys(globals).length > 0 && (
            <tr className="section"><td colSpan={2}>globals</td></tr>
          )}
          {showGlobals && Object.entries(globals).map(([n, v]) => row(n, v, "global"))}
        </tbody>
      </table>
      {Object.keys(frame?.locals ?? {}).length === 0 && !showGlobals && (
        <div className="muted pad">no bindings yet</div>
      )}
    </div>
  );
}

/* ----------------------------------------------------------------- call stack */
export function CallStackPanel({ state }: { state: ExecutionState }) {
  return (
    <div className="panel-body callstack">
      {[...state.frames].reverse().map((frame: Frame, i) => (
        <div key={frame.frame_id} className={`frame${i === 0 ? " active" : ""}`}>
          <span className="fname">{frame.name}</span>
          <span className="fline">line {frame.line}</span>
          {frame.return_value && (
            <span className="fret">→ {preview(frame.return_value, 14)}</span>
          )}
        </div>
      ))}
      {state.exception && (
        <div className="frame exception">
          {state.exception.exc_type}: {state.exception.message}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------- timeline */
/** Fixed row height, so the virtualiser can map scroll offset to row index. */
const ROW_HEIGHT = 18;

export function TimelinePanel({
  events, step, onSeek,
}: {
  events: AsEvent[];
  step: number;
  onSeek: (step: number) => void;
}) {
  const [filter, setFilter] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const out: { index: number; ev: AsEvent; text: string; cat: string }[] = [];
    for (let i = 0; i < events.length; i++) {
      const ev = events[i];
      const cat = categoryOf(ev);
      if (filter.size && !filter.has(cat)) continue;
      const text = summarize(ev);
      if (q && !text.toLowerCase().includes(q) && !ev.type.toLowerCase().includes(q)) continue;
      out.push({ index: i, ev, text, cat });
      if (out.length > 4000) break;
    }
    return out;
  }, [events, filter, query]);

  const toggle = (cat: string) =>
    setFilter((current) => {
      const next = new Set(current);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });

  const present = useMemo(() => {
    const seen = new Set<string>();
    for (const ev of events) seen.add(categoryOf(ev));
    return CATEGORY_ORDER.filter((c) => seen.has(c));
  }, [events]);

  // Only the rows near the viewport are mounted. Without this, every playback
  // step re-rendered the entire event list -- 440 rows for Dijkstra, tens of
  // thousands for a backtracking search -- and playback ran far below the
  // requested speed because each step was waiting on layout.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(320);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const measure = () => setViewportHeight(element.clientHeight || 320);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Keep the current step in view while playing, but never fight the user: only
  // scroll when the row has actually left the window.
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    const index = rows.findIndex((r) => r.index === step);
    if (index < 0) return;
    const top = index * ROW_HEIGHT;
    if (top < element.scrollTop || top > element.scrollTop + element.clientHeight - ROW_HEIGHT) {
      element.scrollTop = Math.max(0, top - element.clientHeight / 2);
    }
  }, [step, rows]);

  const overscan = 10;
  const firstVisible = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - overscan);
  const visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + overscan * 2;
  const windowed = rows.slice(firstVisible, firstVisible + visibleCount);

  return (
    <div className="panel-body timeline">
      <div className="timeline-controls">
        {present.map((cat) => (
          <button
            key={cat}
            className={`chip-btn${filter.size === 0 || filter.has(cat) ? " on" : ""} cat-${cat}`}
            onClick={() => toggle(cat)}
          >
            {cat}
          </button>
        ))}
        <input
          className="search"
          type="search"
          aria-label="Search the timeline"
          placeholder="search events…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">{rows.length} shown</span>
      </div>
      <div
        className="timeline-rows"
        ref={scrollRef}
        onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
      >
        {/* A spacer of the full height keeps the scrollbar honest while only a
            window of rows is actually mounted. */}
        <div style={{ height: rows.length * ROW_HEIGHT, position: "relative" }}>
          {windowed.map(({ index, ev, text, cat }, i) => (
            <div
              key={index}
              className={`trow cat-${cat}${index === step ? " current" : ""}${
                ev.meta?.origin === "lifted" ? " lifted" : ""
              }`}
              style={{
                position: "absolute",
                top: (firstVisible + i) * ROW_HEIGHT,
                left: 0,
                right: 0,
                height: ROW_HEIGHT,
                paddingLeft: 6 + ev.depth * 12,
              }}
              onClick={() => onSeek(index)}
              title={ev.meta?.origin === "lifted" ? "inferred from generic events" : undefined}
            >
              <span className="tstep">{index}</span>
              <span className="tline">{ev.loc?.line ?? ""}</span>
              <span className="ttext">{text}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------- console */
export function ConsolePanel({ state }: { state: ExecutionState }) {
  return (
    <div className="panel-body console">
      <pre>{state.stdout || <span className="muted">no output yet</span>}</pre>
      {state.stderr && <pre className="stderr">{state.stderr}</pre>}
    </div>
  );
}

/* ------------------------------------------------------------------ analytics */
export function AnalyticsPanel({
  analytics, state,
}: {
  analytics: Analytics;
  state: ExecutionState;
}) {
  const origins = analytics.event_origins ?? { recorded: 0, lifted: 0, semantic: 0 };
  const total = Math.max(1, origins.recorded + origins.lifted + origins.semantic);
  return (
    <div className="panel-body analytics">
      <div className="metric-grid">
        {Object.entries(analytics.metrics ?? {})
          .sort(([a], [b]) => a.localeCompare(b))
          .map(([key, value]) => (
            <div key={key} className="metric">
              <span className="mv">{value}</span>
              <span className="mk">{formatMetric(key)}</span>
            </div>
          ))}
        <div className="metric">
          <span className="mv">{analytics.max_depth}</span>
          <span className="mk">max depth</span>
        </div>
        <div className="metric">
          <span className="mv">{analytics.duration_ms.toFixed(1)}</span>
          <span className="mk">ms in sandbox</span>
        </div>
      </div>

      <h4>Where the events came from</h4>
      <div className="origin-bar">
        <span className="recorded" style={{ width: `${(origins.recorded / total) * 100}%` }} />
        <span className="lifted" style={{ width: `${(origins.lifted / total) * 100}%` }} />
        <span className="semantic" style={{ width: `${(origins.semantic / total) * 100}%` }} />
      </div>
      <div className="origin-legend">
        <span><i className="recorded" /> recorded {origins.recorded}</span>
        <span><i className="lifted" /> inferred {origins.lifted}</span>
        <span><i className="semantic" /> annotated {origins.semantic}</span>
      </div>

      {Object.keys(analytics.function_calls ?? {}).length > 0 && (
        <>
          <h4>Calls</h4>
          <div className="metric-grid">
            {Object.entries(analytics.function_calls).map(([name, count]) => (
              <div key={name} className="metric">
                <span className="mv">{count}</span>
                <span className="mk">{name}()</span>
              </div>
            ))}
          </div>
        </>
      )}

      <h4>Live counters at step {state.step}</h4>
      <div className="metric-grid">
        {Object.entries(state.counters).map(([key, value]) => (
          <div key={key} className="metric small">
            <span className="mv">{value}</span>
            <span className="mk">{formatMetric(key)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
