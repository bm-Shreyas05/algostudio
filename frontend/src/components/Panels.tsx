import { useEffect, useMemo, useRef, useState } from "react";
import type {
  Analytics, AsEvent, EncodedValue, ExecutionState, Frame,
} from "../api/types";
import {
  categoryOf, CATEGORY_ORDER, formatMetric, previewContents, previewLive, renderHeap, summarize,
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

  // At the end every function has returned, so only the module is left on
  // the stack -- and a catalogue algorithm's module has no variables of its
  // own. The panel used to say "No variables yet" at the very moment the
  // answer was ready. Show what the outermost call finished with instead.
  const finished = Boolean(state.finished_reason);
  const lastCall = finished && Object.keys(frame?.locals ?? {}).length === 0
    ? outermostReturned(state)
    : null;

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
        <td className="k">
          {/* A real button: this cell was clickable before, but only to a
              mouse -- a keyboard could not reach it at all. */}
          <button
            type="button"
            className="var-name"
            onClick={() => onInspect(name)}
            title={`Jump to where ${name} last changed, and ask the tutor about it`}
          >
            {name}
          </button>
        </td>
        <td className="v">
          {wasWritten && changed!.old && (
            <span className="old">{previewLive(changed!.old, state.heap, 18)} →</span>
          )}{" "}
          {previewContents(value, state.heap, 48)}
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
      {/* The call stack, as the breadcrumb it really is. It used to be a tab of
          its own, which meant the values and the call they belonged to were
          never on screen together. */}
      {state.frames.length > 1 && (
        <nav className="stack-crumbs" aria-label="Call stack">
          {state.frames.map((f, i) => (
            <span key={f.frame_id} className={i === state.frames.length - 1 ? "now" : ""}>
              {f.name === "<module>" ? "program" : `${f.name}()`}
            </span>
          ))}
        </nav>
      )}
      {state.exception && (
        <div className="var-exception">
          {state.exception.exc_type}: {state.exception.message}
        </div>
      )}
      {finished && (
        <p className="var-finished">
          {lastCall ? (
            <>
              Finished. These are the values <code>{lastCall.name}()</code> ended with
              {lastCall.return_value && (
                <>; it returned <code>{previewContents(lastCall.return_value, state.heap, 48)}</code></>
              )}.
            </>
          ) : Object.keys(frame?.locals ?? {}).length ? (
            "Finished. These are the values the program ended with."
          ) : (
            "Finished. This program kept no variables."
          )}
        </p>
      )}
      <table>
        <tbody>
          {Object.entries(frame?.locals ?? {}).map(([n, v]) => row(n, v, "local"))}
          {lastCall && Object.entries(lastCall.locals).map(([n, v]) => row(n, v, "final"))}
          {showGlobals && Object.keys(globals).length > 0 && (
            <tr className="section"><td colSpan={2}>outside any function</td></tr>
          )}
          {showGlobals && Object.entries(globals).map(([n, v]) => row(n, v, "global"))}
        </tbody>
      </table>
      {Object.keys(frame?.locals ?? {}).length === 0 && !showGlobals && !lastCall && !finished && (
        <p className="tab-empty">No variables yet — they appear here as the program creates them.</p>
      )}
    </div>
  );
}

/** The last call made from the top level of the program, once it has returned. */
function outermostReturned(state: ExecutionState): Frame | null {
  const moduleId = state.frames[0]?.frame_id ?? 0;
  const calls = Object.values(state.retired)
    .filter((f) => f.parent === moduleId)
    .sort((a, b) => a.frame_id - b.frame_id);
  return calls.length ? calls[calls.length - 1] : null;
}

/* ------------------------------------------------------------------- timeline */
/** Fixed row height, so the virtualiser can map scroll offset to row index.
 *  24px, up from 18: at 12.5px text an 18px row left no air between lines. */
const ROW_HEIGHT = 24;

export function TimelinePanel({
  events, step, onSeek,
}: {
  events: AsEvent[];
  step: number;
  onSeek: (step: number) => void;
}) {
  const [filter, setFilter] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  // Ten category chips are a power tool. They stay one click away rather than
  // occupying the top of the list for everyone.
  const [showFilters, setShowFilters] = useState(false);

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
        <input
          className="search"
          type="search"
          aria-label="Search the steps"
          placeholder="Search steps…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          type="button"
          className={`chip-btn${showFilters || filter.size ? " on" : ""}`}
          aria-expanded={showFilters}
          onClick={() => setShowFilters((v) => !v)}
        >
          Filter{filter.size ? ` (${filter.size})` : ""}
        </button>
        <span className="muted tl-count">
          {rows.length === events.length ? `${rows.length} steps` : `${rows.length} of ${events.length}`}
        </span>
        <span className="muted tl-hint">Click any step to jump to it</span>
      </div>
      {showFilters && (
        <div className="timeline-filters" role="group" aria-label="Show only">
          {present.map((cat) => (
            <button
              key={cat}
              className={`chip-btn${filter.has(cat) ? " on" : ""} cat-${cat}`}
              aria-pressed={filter.has(cat)}
              onClick={() => toggle(cat)}
            >
              {cat}
            </button>
          ))}
          {filter.size > 0 && (
            <button type="button" className="linkish" onClick={() => setFilter(new Set())}>
              Show all
            </button>
          )}
        </div>
      )}
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
              {/* One number, not two: an unlabelled event index beside an
                  unlabelled line number read as a rendering fault. */}
              <span className="tline" title="source line">{ev.loc?.line ? `L${ev.loc.line}` : ""}</span>
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
      {state.stdout || state.stderr ? (
        <>
          {state.stdout && <pre>{state.stdout}</pre>}
          {state.stderr && <pre className="stderr">{state.stderr}</pre>}
        </>
      ) : (
        <p className="tab-empty">
          Nothing printed yet. Anything the program <code>print</code>s appears
          here, up to the current step.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ analytics */
/**
 * The measures worth showing, in plain words, in the order they matter.
 *
 * Anything the engine counts but no learner asks about -- how many conditions
 * were evaluated, how many branches were taken, how many objects were
 * allocated -- stays out unless an algorithm names it as its own measure.
 */
const MEASURES: Record<string, { one: string; many: string; hint: string }> = {
  statements: {
    one: "line run", many: "lines run",
    hint: "Lines of code executed, counting a line again every time a loop repeats it.",
  },
  element_comparisons: {
    one: "item comparison", many: "item comparisons",
    hint: "Two items of the data compared with each other, such as arr[j] > arr[j + 1] — the usual way to measure the cost of sorting and searching.",
  },
  comparisons: {
    one: "comparison", many: "comparisons",
    hint: "Every comparison the program evaluated (<, >, ==, …), including ones between plain numbers.",
  },
  swaps: { one: "swap", many: "swaps", hint: "Two items exchanged in place." },
  array_reads: {
    one: "item read", many: "item reads",
    hint: "One item read from a list or dictionary, such as arr[i].",
  },
  array_writes: {
    one: "item write", many: "item writes",
    hint: "One item stored into a list or dictionary, such as arr[i] = x.",
  },
  loop_iterations: {
    one: "loop pass", many: "loop passes",
    hint: "Times a loop body started, across every loop in the program.",
  },
  function_calls: {
    one: "function call", many: "function calls",
    hint: "Calls to functions the program defines.",
  },
  visits: { one: "node visited", many: "nodes visited", hint: "Nodes the algorithm finished with." },
  discoveries: { one: "node discovered", many: "nodes discovered", hint: "Nodes reached for the first time." },
  relaxations: {
    one: "edge relaxation", many: "edge relaxations",
    hint: "Edges checked for a shorter route.",
  },
  enqueues: { one: "enqueue", many: "enqueues", hint: "Items added to a queue." },
  dequeues: { one: "dequeue", many: "dequeues", hint: "Items taken off a queue." },
  // Counted from append() and pop(), whether or not the list is used as a stack.
  pushes: { one: "append", many: "appends", hint: "Items added to the end of a list, such as order.append(x)." },
  pops: { one: "pop", many: "pops", hint: "Items taken off a list with pop()." },
  merges: { one: "merge", many: "merges", hint: "Sorted runs merged into one." },
  partitions: { one: "partition", many: "partitions", hint: "Times a range was split around a pivot." },
  // Shown only when an algorithm names one of these as its own measure.
  conditions: {
    one: "condition checked", many: "conditions checked",
    hint: "Tests evaluated by if and while statements.",
  },
  mutations: {
    one: "in-place change", many: "in-place changes",
    hint: "Calls that changed a list, set or dictionary in place, such as append or pop.",
  },
  attribute_writes: {
    one: "field write", many: "field writes",
    hint: "Values stored into an object's fields, such as node.next = x.",
  },
};

/** Always worth showing when non-zero; the rest only when an algorithm asks. */
const EVERYDAY = [
  "statements", "element_comparisons", "comparisons", "swaps", "array_reads",
  "array_writes", "loop_iterations", "function_calls", "visits", "discoveries",
  "relaxations", "enqueues", "dequeues", "pushes", "pops", "merges", "partitions",
];

function measureLabel(key: string, value: number): string {
  const known = MEASURES[key];
  if (known) return value === 1 ? known.one : known.many;
  return formatMetric(key);
}

export function AnalyticsPanel({
  analytics, emphasis = [], canEdit = false,
}: {
  analytics: Analytics;
  /** The measures the loaded algorithm declares for itself, shown first. */
  emphasis?: string[];
  /** Whether "Edit code" exists here, so the note can point at it. */
  canEdit?: boolean;
}) {
  // What a learner compares between two algorithms: how much work each did.
  // Where the engine's events came from and how long the sandbox took are
  // facts about the tool, not the program, and stay out. So does the running
  // "so far" tally that used to sit under the totals: the headline above the
  // picture already counts up live as the run plays.
  const values: Record<string, number> = { ...(analytics.metrics ?? {}) };
  if (analytics.max_depth > 1) values.max_depth = analytics.max_depth;
  // In most sorts every comparison *is* between two items, and "14 item
  // comparisons" beside "14 comparisons" reads as the same fact twice.
  if (values.element_comparisons === values.comparisons) delete values.element_comparisons;

  const order = [
    ...emphasis,
    ...EVERYDAY,
    ...(analytics.max_depth > 1 ? ["max_depth"] : []),
  ];
  const shown = order
    .filter((key, i) => order.indexOf(key) === i)
    .filter((key) => typeof values[key] === "number" && values[key] > 0);

  // Per-function counts only say something when a function ran more than
  // once -- "bubble_sort() 1" is not news.
  const calls = Object.entries(analytics.function_calls ?? {});
  const repeated = calls.some(([, count]) => count > 1);

  return (
    <div className="panel-body analytics">
      <h4>Work done by the whole run</h4>
      <div className="metric-grid">
        {shown.map((key) => (
          <div
            key={key}
            className={`metric${emphasis.includes(key) ? " key" : ""}`}
            title={
              key === "max_depth"
                ? "The most calls that were waiting on one another at the same moment."
                : MEASURES[key]?.hint
            }
          >
            <span className="mv">{values[key].toLocaleString()}</span>
            <span className="mk">
              {key === "max_depth" ? "calls deep at most" : measureLabel(key, values[key])}
            </span>
          </div>
        ))}
      </div>
      {emphasis.length > 0 && (
        <p className="stats-note">
          Highlighted: what this algorithm is usually measured by.
          {canEdit && (
            <> To see how fast they grow, choose <strong>Edit code</strong> and
            run it on a bigger input.</>
          )}
        </p>
      )}

      {repeated && (
        <>
          <h4>Calls to each function</h4>
          <div className="metric-grid">
            {calls.map(([name, count]) => (
              <div key={name} className="metric">
                <span className="mv">{count.toLocaleString()}</span>
                <span className="mk">{name}()</span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
