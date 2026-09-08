import { useMemo, useState } from "react";
import type {
  Analytics, AsEvent, EncodedValue, ExecutionState, Frame,
} from "../api/types";
import {
  categoryOf, CATEGORY_ORDER, formatMetric, preview, previewLive, renderHeap, summarize,
} from "../lib/format";

/* ------------------------------------------------------------------ variables */
export function VariablesPanel({
  state, previousLocals, onInspect,
}: {
  state: ExecutionState;
  previousLocals: Record<string, EncodedValue>;
  onInspect: (name: string) => void;
}) {
  const frame = state.frames[state.frames.length - 1];
  const globals = state.frames[0]?.locals ?? {};
  const showGlobals = state.frames.length > 1;

  const row = (name: string, value: EncodedValue, scope: string) => {
    const before = previousLocals[name];
    const changed = before !== undefined && JSON.stringify(before) !== JSON.stringify(value);
    const isNew = before === undefined;
    const ref = (value as any)?.k === "ref" ? (value as any).r : null;
    return (
      <tr key={`${scope}-${name}`} className={changed ? "changed" : isNew ? "created" : undefined}>
        <td className="k" onClick={() => onInspect(name)} title="show where this changed">
          {name}
        </td>
        <td className="v">
          {changed && (
            <span className="old">{previewLive(before, state.heap, 18)} →</span>
          )}{" "}
          {previewLive(value, state.heap, 34)}
          {ref && (
            <span className="ref-badge" title={renderHeap(state.heap[ref])}>
              {ref}
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
          placeholder="search events…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">{rows.length} shown</span>
      </div>
      <div className="timeline-rows">
        {rows.map(({ index, ev, text, cat }) => (
          <div
            key={index}
            className={`trow cat-${cat}${index === step ? " current" : ""}${
              ev.meta?.origin === "lifted" ? " lifted" : ""
            }`}
            style={{ paddingLeft: 6 + ev.depth * 12 }}
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
