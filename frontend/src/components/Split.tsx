import {
  Children, useCallback, useEffect, useRef, useState, type ReactNode,
} from "react";

/**
 * A draggable split container.
 *
 * Panes are sized as percentages of the container so the layout survives window
 * resizes, and the sizes are persisted per `storageKey` so a layout the user
 * arranged is still there next session.
 *
 * Sizing lives here rather than in CSS because the whole point is that the user
 * decides: a canvas showing a 40-node graph needs room that a fixed
 * `grid-template-columns` cannot give it.
 */
export interface SplitProps {
  direction: "row" | "column";
  storageKey: string;
  /** Initial sizes as percentages; must be the same length as `children`. */
  initial: number[];
  /** Minimum size per pane, in pixels. Prevents a pane from vanishing. */
  minPx?: number;
  children: ReactNode;
  className?: string;
  /** Landmark id, so a skip link has somewhere to land. */
  id?: string;
}

function load(key: string, fallback: number[]): number[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw);
    if (
      Array.isArray(parsed) &&
      parsed.length === fallback.length &&
      parsed.every((n) => typeof n === "number" && n > 0)
    ) {
      return parsed;
    }
  } catch {
    /* corrupt or unavailable storage: fall back to the default layout */
  }
  return fallback;
}

export function Split({
  direction, storageKey, initial, minPx = 90, children, className = "", id,
}: SplitProps) {
  const panes = Children.toArray(children);
  const [sizes, setSizes] = useState<number[]>(() => load(storageKey, initial));
  const containerRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{ index: number; start: number; before: number; after: number } | null>(null);

  // A pane count change (a tab appearing, say) invalidates saved sizes.
  useEffect(() => {
    if (sizes.length !== panes.length) setSizes(initial);
  }, [panes.length, initial, sizes.length]);

  const persist = useCallback(
    (next: number[]) => {
      setSizes(next);
      try {
        localStorage.setItem(storageKey, JSON.stringify(next));
      } catch {
        /* private mode: the layout just will not persist */
      }
    },
    [storageKey],
  );

  const onPointerDown = (index: number) => (e: React.PointerEvent) => {
    e.preventDefault();
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    // Suppress text selection for the duration of the drag: without it, sweeping
    // across the source pane highlights half the program.
    document.body.classList.add(direction === "row" ? "resizing-col" : "resizing-row");
    drag.current = {
      index,
      start: direction === "row" ? e.clientX : e.clientY,
      before: sizes[index],
      after: sizes[index + 1],
    };
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const state = drag.current;
    const container = containerRef.current;
    if (!state || !container) return;
    const total =
      direction === "row" ? container.clientWidth : container.clientHeight;
    if (total <= 0) return;

    const position = direction === "row" ? e.clientX : e.clientY;
    const deltaPct = ((position - state.start) / total) * 100;
    const minPct = (minPx / total) * 100;
    const pair = state.before + state.after;

    // Clamp so neither neighbour drops below its minimum; everything else in
    // the container keeps its size, so a drag only moves one boundary.
    const before = Math.max(minPct, Math.min(pair - minPct, state.before + deltaPct));
    const next = [...sizes];
    next[state.index] = before;
    next[state.index + 1] = pair - before;
    setSizes(next);
  };

  const onPointerUp = (e: React.PointerEvent) => {
    if (!drag.current) return;
    (e.target as HTMLElement).releasePointerCapture(e.pointerId);
    document.body.classList.remove("resizing-col", "resizing-row");
    drag.current = null;
    persist(sizes);
  };

  useEffect(() => () => {
    document.body.classList.remove("resizing-col", "resizing-row");
  }, []);

  const reset = () => persist(initial);

  return (
    <div
      ref={containerRef}
      id={id}
      className={`split split-${direction} ${className}`}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      {panes.map((pane, i) => (
        <div key={i} className="split-pane" style={{ flexBasis: `${sizes[i] ?? 0}%` }}>
          {pane}
          {i < panes.length - 1 && (
            <div
              className={`split-handle handle-${direction}`}
              onPointerDown={onPointerDown(i)}
              onDoubleClick={reset}
              role="separator"
              aria-orientation={direction === "row" ? "vertical" : "horizontal"}
              title="drag to resize · double-click to reset"
            />
          )}
        </div>
      ))}
    </div>
  );
}

/**
 * A pane header with collapse and maximize affordances.
 *
 * Maximize is the direct answer to "the visualization gets blocked by the
 * sections below it": one click gives a view the whole window, and clicking
 * again puts the layout back exactly as it was.
 */
export function PaneHead({
  title, extra, collapsed, onToggleCollapse, maximized, onToggleMaximize,
}: {
  title: ReactNode;
  extra?: ReactNode;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  maximized?: boolean;
  onToggleMaximize?: () => void;
}) {
  return (
    <div className="pane-head">
      {onToggleCollapse && (
        <button
          className="pane-btn"
          onClick={onToggleCollapse}
          title={collapsed ? "expand" : "collapse"}
          // The label cannot come from the glyph: a screen reader announces
          // "▾" as nothing useful, or as "down pointing triangle".
          aria-label={`${collapsed ? "Expand" : "Collapse"} the ${title} panel`}
          aria-expanded={!collapsed}
        >
          {collapsed ? "▸" : "▾"}
        </button>
      )}
      <span className="pane-title">{title}</span>
      <span className="grow" />
      {extra}
      {onToggleMaximize && (
        <button
          className="pane-btn pane-maximize"
          onClick={onToggleMaximize}
          title={maximized ? "restore layout" : "maximize this panel"}
          aria-label={
            maximized ? "Restore the layout" : `Maximize the ${title} panel`
          }
          aria-pressed={Boolean(maximized)}
        >
          {maximized ? "🗗" : "⛶"}
        </button>
      )}
    </div>
  );
}
