import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { AlgorithmPlugin } from "../api/types";

/** Display order and names: the order a course would teach them in. */
export const CATEGORIES: [string, string][] = [
  ["sorting", "Sorting"],
  ["search", "Searching"],
  ["graph", "Graphs"],
  ["tree", "Trees"],
  ["dynamic-programming", "Dynamic programming"],
  ["backtracking", "Backtracking"],
  ["string", "Strings"],
  ["math", "Number theory"],
  ["data-structure", "Data structures"],
];
const CATEGORY_NAME = Object.fromEntries(CATEGORIES);
const CATEGORY_RANK = Object.fromEntries(CATEGORIES.map(([id], i) => [id, i]));

interface Props {
  open: boolean;
  algorithms: AlgorithmPlugin[];
  currentId: string;
  onClose: () => void;
  onPick: (id: string) => void;
  /** Leave the catalogue and write code instead. */
  onWriteOwn: () => void;
}

/**
 * The catalogue, as a searchable palette.
 *
 * This replaces a native <select> holding 49 options, which was the main way
 * into the product and the worst part of it: no search, no descriptions, and
 * categories visible only once it was already open. A palette is the pattern
 * people already know from editors -- type a few letters, Enter -- and it can
 * show *why* you might pick something, not just its name.
 *
 * Built as a proper modal: focus moves in on open and back out on close, Tab is
 * contained while it is open, Escape dismisses, and the list is a listbox the
 * input drives through aria-activedescendant, so a screen reader hears the
 * option under the cursor as the arrow keys move it.
 */
export function AlgorithmBrowser({
  open, algorithms, currentId, onClose, onPick, onWriteOwn,
}: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreRef = useRef<Element | null>(null);
  const baseId = useId();

  const searching = query.trim().length > 0;

  const results = useMemo(() => {
    if (!searching) {
      // Browsing: the whole catalogue, grouped in teaching order.
      return [...algorithms].sort((x, y) =>
        (CATEGORY_RANK[x.category] ?? 99) - (CATEGORY_RANK[y.category] ?? 99) ||
        x.name.localeCompare(y.name));
    }
    // Searching: ranked, because "every word appears somewhere" is too weak on
    // its own. The first version did only that, and "n log n" returned binary
    // search and Euclid's GCD -- the word "n" appears in nearly everything, so
    // the query collapsed to "contains log". A whole-phrase hit on the
    // complexity now outranks scattered words, which still match, lower down.
    const q = query.trim().toLowerCase();
    const words = q.split(/\s+/);
    const scored = algorithms.map((a) => {
      const name = a.name.toLowerCase();
      const cx = `${a.complexity?.time ?? ""} ${a.complexity?.space ?? ""}`.toLowerCase();
      const cat = `${a.category} ${CATEGORY_NAME[a.category] ?? ""}`.toLowerCase();
      const tags = (a.tags ?? []).join(" ").toLowerCase();
      const desc = a.description.toLowerCase();
      const hay = `${name} ${cx} ${cat} ${tags} ${desc}`;
      let score = 0;
      if (name === q) score = 1000;
      else if (name.startsWith(q)) score = 800;
      else if (name.includes(q)) score = 600;
      else if (cx.includes(q)) score = 500;
      else if (cat.includes(q) || tags.includes(q)) score = 400;
      else if (desc.includes(q)) score = 200;
      else if (words.every((w) => hay.includes(w))) {
        score = 50 + words.filter((w) => name.includes(w)).length * 10;
      }
      return { a, score };
    });
    return scored
      .filter((s) => s.score > 0)
      .sort((x, y) => y.score - x.score || x.a.name.localeCompare(y.a.name))
      .map((s) => s.a);
  }, [algorithms, query, searching]);

  // Open: remember what had focus, reset, focus the search box.
  useEffect(() => {
    if (!open) return;
    restoreRef.current = document.activeElement;
    setQuery("");
    const current = algorithms.findIndex((a) => a.id === currentId);
    setActive(Math.max(0, current));
    requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      (restoreRef.current as HTMLElement | null)?.focus?.();
    };
  }, [open]);                                           // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setActive(0); }, [query]);

  // Keep the highlighted option in view as the arrow keys move it.
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, results]);

  if (!open) return null;

  const choose = (index: number) => {
    const pick = results[index];
    if (pick) onPick(pick.id);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(results.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Home" && e.ctrlKey) {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End" && e.ctrlKey) {
      e.preventDefault();
      setActive(results.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Tab") {
      // Contain focus: the only other focusable things are the buttons.
      const focusables = dialogRef.current?.querySelectorAll<HTMLElement>(
        "input, button:not([disabled])",
      );
      if (!focusables?.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };

  // Group the flat, sorted result list under category headings while keeping
  // one running index, so keyboard navigation crosses groups seamlessly.
  // While searching the list is ranked, so grouping it would split one
  // category into several runs; show it as one list and name each category.
  const groups: { category: string; items: { algo: AlgorithmPlugin; index: number }[] }[] = [];
  results.forEach((algo, index) => {
    const key = searching ? "__results" : algo.category;
    const last = groups[groups.length - 1];
    if (last && last.category === key) last.items.push({ algo, index });
    else groups.push({ category: key, items: [{ algo, index }] });
  });

  const optionId = (i: number) => `${baseId}-opt-${i}`;

  return (
    <div className="palette-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={dialogRef}
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        onKeyDown={onKeyDown}
      >
        <div className="palette-head">
          <h2 id={`${baseId}-title`} className="visually-hidden">Choose an algorithm</h2>
          <svg className="palette-search-icon" viewBox="0 0 20 20" aria-hidden="true">
            <circle cx="8.5" cy="8.5" r="5.5" fill="none" stroke="currentColor" strokeWidth="2" />
            <path d="M13 13l4 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
          <input
            ref={inputRef}
            className="palette-input"
            type="text"
            role="combobox"
            aria-label="Search algorithms"
            aria-expanded="true"
            aria-controls={`${baseId}-list`}
            aria-activedescendant={results.length ? optionId(active) : undefined}
            aria-autocomplete="list"
            placeholder={`Search ${algorithms.length} algorithms — try “graph”, “O(n log n)”, “queue”…`}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <kbd className="palette-esc">Esc</kbd>
        </div>

        <ul
          ref={listRef}
          id={`${baseId}-list`}
          className="palette-list"
          role="listbox"
          aria-label="Algorithms"
        >
          {groups.map((group) => (
            <li key={group.category} role="presentation" className="palette-group">
              <div className="palette-group-name" role="presentation">
                {group.category === "__results"
                  ? "Best matches"
                  : CATEGORY_NAME[group.category] ?? group.category}
                <span>{group.items.length}</span>
              </div>
              <ul role="presentation">
                {group.items.map(({ algo, index }) => (
                  <li
                    key={algo.id}
                    id={optionId(index)}
                    data-index={index}
                    role="option"
                    aria-selected={index === active}
                    className={
                      "palette-item" +
                      (index === active ? " active" : "") +
                      (algo.id === currentId ? " current" : "")
                    }
                    onMouseMove={() => index !== active && setActive(index)}
                    onClick={() => choose(index)}
                  >
                    <div className="pi-top">
                      <span className="pi-name">{algo.name}</span>
                      {searching && (
                        <span className="pi-cat">{CATEGORY_NAME[algo.category] ?? algo.category}</span>
                      )}
                      {algo.id === currentId && <span className="pi-now">loaded</span>}
                      {algo.complexity && <span className="pi-cx">{algo.complexity.time}</span>}
                    </div>
                    <div className="pi-desc">{algo.description}</div>
                  </li>
                ))}
              </ul>
            </li>
          ))}
          {!results.length && (
            <li className="palette-empty" role="presentation">
              Nothing matches “{query}”. The catalogue is searched by name,
              category, tag and complexity.
            </li>
          )}
        </ul>

        <div className="palette-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span><kbd>Enter</kbd> run</span>
          <span><kbd>Esc</kbd> close</span>
          <button type="button" className="palette-own" onClick={onWriteOwn}>
            Write your own code instead
          </button>
        </div>
      </div>
    </div>
  );
}
