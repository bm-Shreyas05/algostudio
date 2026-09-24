import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { AlgorithmPlugin, EncodedValue, HeapObject } from "./api/types";
import type { ChangedBinding } from "./components/Panels";
import { AIPanel } from "./components/AIPanel";
import { AlgorithmBrowser } from "./components/AlgorithmBrowser";
import { FocusStrip } from "./components/FocusStrip";
import { Icon } from "./components/Icon";
import { Popover } from "./components/Popover";
import {
  AnalyticsPanel, ConsolePanel, TimelinePanel, VariablesPanel,
} from "./components/Panels";
import { SourceView } from "./components/SourceView";
import { PaneHead, Split } from "./components/Split";
import { Transport } from "./components/Transport";
import { browserEngineAvailable } from "./engine/browserEngine";
import { liveAnnotations } from "./engine/reducer";
import { MOBILE_QUERY, useMediaQuery } from "./lib/useMediaQuery";
import { useExecution } from "./store/useExecution";
import { resolveView, VIEW_LABELS } from "./views/registry";
import { CallTreeView } from "./views/TreeView";
import { annotationsFor } from "./views/types";

const STARTER = `x = 5
for i in range(5):
    x += i
print("total is", x)
`;

/**
 * Three regions, not four. The old layout gave variables a column of their own,
 * squeezing the visualization -- the actual product -- into the middle third
 * of the screen, and put the raw event log underneath everything by default.
 * Now: the code and everything *about* the run on the left, the picture of the
 * run on the right, as tall and wide as the window allows.
 */
type DetailTab = "variables" | "output" | "explain" | "steps" | "stats";
type PaneId = "source" | "canvas" | "details";

const DETAIL_TABS: [DetailTab, string][] = [
  ["variables", "Variables"],
  ["output", "Output"],
  ["explain", "Explain"],
  ["steps", "Steps"],
  ["stats", "Stats"],
];

/**
 * The four shown on the empty canvas. Chosen so that each one lands on a
 * different view -- an array, a graph, a tree, a table -- which is the fastest
 * possible demonstration that the pictures are derived rather than drawn.
 */
const FEATURED: { id: string; view: string; hint: string }[] = [
  { id: "bubble_sort", view: "Array", hint: "Watch swaps and comparisons on a list" },
  { id: "bfs", view: "Graph", hint: "Follow a traversal node by node" },
  { id: "tree_traversals", view: "Tree", hint: "See recursion walk a tree" },
  { id: "edit_distance", view: "Table", hint: "Fill a dynamic-programming grid" },
];

/** Plain-English names for the instrumentation levels. */
const GRANULARITY: { id: string; label: string; detail: string }[] = [
  { id: "minimal", label: "Statements", detail: "One step per line. Fastest; least detail." },
  { id: "standard", label: "Expressions", detail: "Every read, write and comparison. The default." },
  { id: "verbose", label: "Everything", detail: "Every sub-expression. Long recordings." },
];

/**
 * " · 6 items" for a container, nothing for anything else.
 *
 * Only a list, tuple, set or dict has a size worth printing. For an object,
 * `n` counts its *fields*, so a binary-tree root read "Tree · 3 items" -- its
 * value, left and right -- on an eight-node tree, which is simply false.
 */
function sizeLabel(obj: HeapObject | undefined, view: string): string {
  if (!obj || typeof obj.n !== "number") return "";
  if (!obj.items && !obj.entries) return "";
  // A list of lists drawn as a grid is counted the way it is drawn.
  const [one, many] = view === "matrix" ? ["row", "rows"] : ["item", "items"];
  return ` · ${obj.n} ${obj.n === 1 ? one : many}`;
}

/** Marks the line "Edit code" appends to a catalogue algorithm, so it is added once. */
const CALL_NOTE = "# How the catalogue runs it. Change the input, then press Run.";

/**
 * Highlights that describe a single moment: the pair just compared, the swap,
 * where `j` pointed. Once the program has finished they describe a moment that
 * is over, and at the end of a sort they left two cells lit as though the
 * comparison were still happening. Marks, regions and visited nodes stay:
 * those describe the result.
 */
const FLEETING = new Set([
  "compare", "highlight", "swap", "relax", "discover", "note",
  "push", "pop", "enqueue", "dequeue", "pointer",
]);

/** Tab order on narrow screens: what you look at most, first. */
const MOBILE_PANES: [PaneId, string][] = [
  ["canvas", "Visual"],
  ["source", "Code"],
  ["details", "Details"],
];

export default function App() {
  const exec = useExecution();
  const [source, setSource] = useState(STARTER);
  const [editing, setEditing] = useState(true);
  const [granularity, setGranularity] = useState("standard");
  const [algorithms, setAlgorithms] = useState<AlgorithmPlugin[]>([]);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState("");
  const [exampleCall, setExampleCall] = useState("");
  const [focusEditor, setFocusEditor] = useState(false);
  const editorFocused = useCallback(() => setFocusEditor(false), []);
  const [detailTab, setDetailTab] = useState<DetailTab>("variables");
  const [focusVariable, setFocusVariable] = useState("");
  const [pinned, setPinned] = useState<Record<string, string>>({});
  const [health, setHealth] = useState<Record<string, any> | null>(null);
  const [maximized, setMaximized] = useState<PaneId | null>(null);
  /* Below the breakpoint there are no dividers to drag, so the four panes
     become one pane plus a tab bar. Same components, same state — only the
     container changes. */
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const [mobilePane, setMobilePane] = useState<PaneId>("canvas");
  const [browserOpen, setBrowserOpen] = useState(false);

  useEffect(() => {
    api.algorithms().then((r) => setAlgorithms(r.algorithms)).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const { bundle, state, timeline } = exec;

  /* A deployment can be published with ALGOSTUDIO_ALLOW_ARBITRARY_CODE=0, which
     serves the bundled catalogue and refuses source typed by a visitor -- the
     honest posture for a public link with no container sandbox under it
     (docs/20-deployment.md). */
  const serverRefusesCode = health?.allow_arbitrary_code === false;

  /* ...but the server refusing is not the same as the app being unable. When
     the in-browser engine is shipped, the visitor's code runs in this tab and
     never reaches the server at all, so the editor works and the server's
     refusal still stands (docs/21-pyodide-spike.md). Only when BOTH are
     unavailable is there genuinely nothing to offer. */
  const [localEngine, setLocalEngine] = useState(false);
  useEffect(() => {
    browserEngineAvailable().then(setLocalEngine).catch(() => setLocalEngine(false));
  }, []);

  const canEdit = !serverRefusesCode || localEngine;
  const runsLocally = serverRefusesCode && localEngine;
  const curated = !canEdit;

  /* ---- which binding this step changed ---------------------------------
     Read straight off the current event. The previous version rebuilt the whole
     prior state (checkpoint clone + replay) on every render just to diff two
     dictionaries, which made playback roughly ten times slower than the speed
     setting asked for. The event already says exactly what changed. */
  const changed = useMemo<ChangedBinding>(() => {
    const ev = bundle && state.step >= 0 ? bundle.events[state.step] : null;
    if (!ev) return null;
    if (ev.type === "VARIABLE_WRITTEN") {
      return { name: ev.payload.name, old: ev.payload.old as EncodedValue, created: false };
    }
    if (ev.type === "VARIABLE_CREATED") {
      return { name: ev.payload.name, old: null, created: true };
    }
    return null;
  }, [bundle, state.step]);

  const annotations = useMemo(() => {
    const live = liveAnnotations(state);
    return state.finished_reason ? live.filter((a) => !FLEETING.has(a.kind)) : live;
  }, [state]);

  const branchLine = useMemo(() => {
    if (!bundle || state.step < 0) return null;
    for (let i = state.step; i >= Math.max(0, state.step - 6); i--) {
      const ev = bundle.events[i];
      if (ev?.type === "BRANCH_TAKEN") return ev.loc?.line ?? null;
    }
    return null;
  }, [bundle, state.step]);

  /* ---- run -------------------------------------------------------------- */
  const loadAlgorithm = useCallback(async (id: string) => {
    setSelectedAlgorithm(id);
    if (!id) return;
    const plugin = await api.algorithm(id);
    setSource(plugin.source ?? "");
    setExampleCall(plugin.example_call ?? "");
    const inputs = Object.fromEntries(plugin.inputs.map((f) => [f.name, f.default]));
    const result = await exec.runAlgorithm(id, inputs, granularity);
    if (result) setEditing(false);
  }, [exec, granularity]);

  const doRun = useCallback(async () => {
    // Showing a catalogue algorithm rather than editing it, Run means "run
    // this again" -- and that has to be the catalogue's run. The source on
    // its own only defines the function, so running it as typed code recorded
    // a def statement and nothing else.
    if (selectedAlgorithm && (!editing || curated)) {
      await loadAlgorithm(selectedAlgorithm);
      return;
    }
    setSelectedAlgorithm("");
    // Where this executes is the whole security story: runsLocally means the
    // source never leaves the tab.
    const result = runsLocally
      ? await exec.runLocal(source, granularity)
      : await exec.run(source, granularity);
    if (result) setEditing(false);
  }, [exec, source, granularity, runsLocally, selectedAlgorithm, editing, curated, loadAlgorithm]);

  /**
   * Open the code in the editor. For a catalogue algorithm, the edit starts
   * from a whole program: the same source plus the call the catalogue makes,
   * so pressing Run does what the catalogue did -- and the input is right
   * there to change.
   */
  const startEditing = useCallback(() => {
    if (selectedAlgorithm && exampleCall && !source.includes(CALL_NOTE)) {
      setSource(`${source.trimEnd()}\n\n\n${CALL_NOTE}\nprint(${exampleCall})\n`);
    }
    setEditing(true);
    setFocusEditor(true);
  }, [selectedAlgorithm, exampleCall, source]);

  const pickAlgorithm = useCallback((id: string) => {
    setBrowserOpen(false);
    loadAlgorithm(id);
    // On a phone the canvas is one tab among four; show the thing just picked.
    setMobilePane("canvas");
  }, [loadAlgorithm]);

  /** Leave the catalogue for the editor, with a clean program to start from. */
  const writeOwn = useCallback(() => {
    setBrowserOpen(false);
    // Keep what they were writing; replace only a bundled algorithm's source,
    // which they did not write and would not expect to be editing.
    if (selectedAlgorithm) setSource(STARTER);
    setSelectedAlgorithm("");
    setEditing(true);
    setMobilePane("source");
    // On a wide screen the editor is already showing, so without this the
    // button appeared to do nothing at all.
    setFocusEditor(true);
  }, [selectedAlgorithm]);

  /* ---- keyboard transport ---------------------------------------------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Ctrl/Cmd+K opens the library from anywhere, including the editor --
      // it is the one shortcut people expect to work while typing.
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setBrowserOpen(true);
        return;
      }
      if (browserOpen) return;               // the palette owns the keyboard

      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      // Space and the arrows already mean something to a focused control:
      // Space presses a button, arrows move a slider or a select. Acting on
      // them here as well made one keypress do two things -- pressing Space on
      // the Back button stepped back *and* toggled playback.
      if (
        editing || target?.isContentEditable ||
        tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" ||
        (tag === "BUTTON" && (e.key === " " || e.key === "Enter"))
      ) return;

      if (e.key === "/") { e.preventDefault(); setBrowserOpen(true); }
      else if (e.key === "ArrowRight") { e.preventDefault(); exec.stepForward(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); exec.stepBack(); }
      else if (e.key === " ") {
        e.preventDefault();
        exec.setTransport((t) => ({ ...t, playing: !t.playing }));
      } else if (e.key === "Escape" && maximized) {
        setMaximized(null);
      } else if (e.key === "Home") {
        e.preventDefault();
        exec.seek(0);
      } else if (e.key === "End") {
        e.preventDefault();
        exec.seek(exec.timeline?.lastStep ?? 0);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, exec, maximized, browserOpen]);

  const inspectVariable = useCallback((name: string) => {
    setFocusVariable(name);
    if (!timeline) return;
    const target = timeline.previousWrite(state.step, name);
    if (target !== null) exec.seek(target);
  }, [timeline, state.step, exec]);

  const plans = useMemo(() => {
    if (!bundle) return [];
    const visible = bundle.views
      .map((v) => (pinned[v.ref] ? { ...v, view: pinned[v.ref] } : v))
      // Synthetic plans (strings, scalar frames) are not heap objects; they
      // bring their own record in props.
      .filter((v) => state.heap[v.ref] || v.props?.record);
    // An object no variable names is almost always structure nested inside one
    // that is named -- BFS's per-node adjacency lists, inside `graph` -- which
    // that card already draws. Showing it again produced cards titled "h7" and
    // "h4": internal heap ids, meaningless to anyone reading. Only when nothing
    // at all is named (a bare expression, a temporary) are they shown.
    const named = visible.filter((v) => v.name);
    return (named.length ? named : visible).slice(0, 6);
  }, [bundle, pinned, state]);

  const plugin = useMemo(
    () => algorithms.find((a) => a.id === selectedAlgorithm) ?? null,
    [algorithms, selectedAlgorithm],
  );

  const statement = useMemo(() => {
    const line = state.current_loc?.line ?? 0;
    const lines = source.split(/\r?\n/);
    return line >= 1 && line <= lines.length ? lines[line - 1].trim() : "";
  }, [source, state.current_loc]);

  const issues = bundle?.summary.capability_report.issues ?? [];
  const lastStep = timeline?.lastStep ?? 0;
  const toggleMax = (id: PaneId) => () =>
    setMaximized((current) => (current === id ? null : id));

  /* ---- panes ------------------------------------------------------------ */
  const sourcePane = (
    <section className="pane source">
      <PaneHead
        title="Code"
        extra={
          // Edit lives with the code it edits, not in the global header. And
          // where the code will run is said here, next to the thing it is
          // about, rather than as a permanent chip at the top of every screen.
          <span className="code-head-extra">
            {editing && !curated ? (
              <>
                {runsLocally && (
                  <span className="engine-note" title="Your code runs in this tab and is never sent to the server">
                    <Icon name="lock" size={13} /> Runs in your browser
                  </span>
                )}
                <span className="kbd-hint"><kbd>Ctrl</kbd>+<kbd>Enter</kbd> to run</span>
              </>
            ) : (
              canEdit && bundle && (
                <button type="button" className="btn-small" onClick={startEditing}>
                  <Icon name="code" size={14} /> Edit code
                </button>
              )
            )}
          </span>
        }
        maximized={maximized === "source"}
        onToggleMaximize={toggleMax("source")}
      />
      <SourceView
        source={source}
        editable={editing && !curated}
        onChange={setSource}
        state={state}
        lineHits={bundle?.analytics.line_hits ?? {}}
        issues={issues}
        breakpoints={exec.breakpoints}
        onToggleBreakpoint={exec.toggleBreakpoint}
        branchLine={branchLine}
        onRun={doRun}
        focusRequested={focusEditor}
        onFocusHandled={editorFocused}
      />
      {exec.breakpoints.size > 0 && (
        <div className="pane-foot">
          <button onClick={() => exec.runToBreakpoint(1)}>Run to next breakpoint</button>
          <button onClick={() => exec.runToBreakpoint(-1)}>Previous</button>
        </div>
      )}
    </section>
  );

  const canvasPane = (
    <section className="pane canvas">
      <PaneHead
        title="Visualization"
        maximized={maximized === "canvas"}
        onToggleMaximize={toggleMax("canvas")}
      />
      {bundle && (
        <FocusStrip
          state={state}
          events={bundle.events}
          step={state.step}
          statement={statement}
        />
      )}
      <div className="canvas-body">
        {!bundle && !exec.busy && (
          <div className="canvas-empty">
            <p className="ce-eyebrow">Start here</p>
            <h2 className="ce-title">Pick something to watch run</h2>
            <p className="ce-lede">
              Each one shows a different kind of picture, worked out from the
              data as the program runs — nothing is drawn by hand.
            </p>

            <div className="featured">
              {FEATURED.map((f) => {
                const algo = algorithms.find((a) => a.id === f.id);
                if (!algo) return null;
                return (
                  <button
                    key={f.id}
                    type="button"
                    className="featured-card"
                    onClick={() => pickAlgorithm(f.id)}
                  >
                    <span className="fc-view">{f.view}</span>
                    <span className="fc-name">{algo.name}</span>
                    <span className="fc-hint">{f.hint}</span>
                    {algo.complexity && <span className="fc-cx">{algo.complexity.time}</span>}
                  </button>
                );
              })}
            </div>

            <div className="ce-more">
              <button type="button" className="btn-secondary" onClick={() => setBrowserOpen(true)}>
                <Icon name="library" />
                Browse all {algorithms.length || 49} algorithms
                {!isMobile && <kbd>Ctrl K</kbd>}
              </button>
              {canEdit && (
                <button type="button" className="btn-ghost" onClick={writeOwn}>
                  <Icon name="code" />
                  Write your own code
                </button>
              )}
            </div>

            {curated && (
              <p className="ce-note">
                This deployment runs the bundled catalogue only — there is no
                container sandbox behind it to run code you write.
              </p>
            )}
          </div>
        )}
        {!bundle && exec.busy && (
          <div className="canvas-loading" role="status">
            <span className="spinner" aria-hidden="true" />
            <span>
              {exec.engineStatus && exec.engineStatus.stage !== "ready"
                ? exec.engineStatus.message
                : "Recording the execution…"}
            </span>
          </div>
        )}
        {plans.map((plan) => {
          const View = resolveView(plan.view);
          return (
            <div key={plan.ref} className="view-card">
              <div className="view-head">
                <strong>{plan.name || `unnamed ${state.heap[plan.ref]?.t ?? "value"}`}</strong>
                {/* The resolver's confidence belongs in the tooltip, for anyone
                    asking why this view was chosen -- not on the card, where a
                    bare "0.87" meant nothing to a learner. The size is what
                    tells two cards both called `arr` apart in a recursion. */}
                <span
                  className="muted"
                  title={`${plan.reason} (confidence ${plan.score.toFixed(2)})`}
                >
                  {VIEW_LABELS[plan.view] ?? plan.view}
                  {sizeLabel(state.heap[plan.ref], plan.view)}
                </span>
                {plan.alternatives.length > 0 && (
                  <select
                    value={plan.view}
                    onChange={(e) => setPinned((p) => ({ ...p, [plan.ref]: e.target.value }))}
                    title="Show this value as a different view"
                    aria-label={`Show ${plan.name || "this value"} as`}
                  >
                    {[plan.view, ...plan.alternatives.map((a) => a.view)]
                      .filter((v, i, arr) => arr.indexOf(v) === i)
                      .map((v) => (
                        <option key={v} value={v}>{VIEW_LABELS[v] ?? v}</option>
                      ))}
                  </select>
                )}
              </div>
              <View
                object={state.heap[plan.ref] ?? (plan.props.record as any)}
                heap={state.heap}
                annotations={annotationsFor(annotations, plan.ref)}
                allAnnotations={annotations}
                state={state}
                descriptor={plan}
              />
            </div>
          );
        })}
        {bundle && state.call_tree.length > 1 && (
          <div className="view-card">
            <div className="view-head">
              <strong>calls</strong>
              <span className="muted">who called whom, and what each returned</span>
            </div>
            <CallTreeView state={state} />
          </div>
        )}
      </div>
    </section>
  );

  // Output is the one tab with news in it; say how much, so nobody has to go
  // looking to find out whether the program printed anything.
  const outputLines = (state.stdout + state.stderr).split(/\r?\n/).filter(Boolean).length;

  const detailsPane = (
    <section className="pane details">
      <div className="pane-head tabs" role="tablist" aria-label="About this run">
        {DETAIL_TABS.map(([tab, label]) => (
          <button
            key={tab}
            role="tab"
            aria-selected={detailTab === tab}
            className={detailTab === tab ? "on" : ""}
            onClick={() => setDetailTab(tab)}
          >
            {label}
            {tab === "output" && outputLines > 0 && <span className="tab-count">{outputLines}</span>}
          </button>
        ))}
        <span className="grow" />
        <button
          className="pane-btn pane-maximize"
          onClick={toggleMax("details")}
          aria-label={maximized === "details" ? "Restore the layout" : "Maximize this panel"}
          title={maximized === "details" ? "restore layout" : "maximize this panel"}
        >
          {maximized === "details" ? "🗗" : "⛶"}
        </button>
      </div>
      <div className="bottom-body" role="tabpanel">
        {detailTab === "variables" && (
          bundle
            ? <VariablesPanel state={state} changed={changed} onInspect={inspectVariable} />
            : <p className="tab-empty">Run something to see its variables change, step by step.</p>
        )}
        {detailTab === "output" && <ConsolePanel state={state} />}
        {detailTab === "explain" && (
          <AIPanel
            executionId={bundle?.summary.execution_id ?? null}
            step={state.step}
            focusVariable={focusVariable}
            local={bundle?.summary.execution_id === "local"}
            llmAvailable={Boolean(health?.ai?.available)}
          />
        )}
        {detailTab === "steps" && (
          bundle
            ? <TimelinePanel events={bundle.events} step={state.step} onSeek={exec.seek} />
            : <p className="tab-empty">Every step of a run is listed here; click one to jump to it.</p>
        )}
        {detailTab === "stats" && (
          bundle
            ? (
              <AnalyticsPanel
                analytics={bundle.analytics}
                emphasis={plugin?.metrics ?? []}
                canEdit={canEdit}
              />
            )
            : <p className="tab-empty">Counts of comparisons, swaps and calls appear here after a run.</p>
        )}
      </div>
    </section>
  );

  const PANES: Record<PaneId, React.ReactNode> = {
    source: sourcePane, canvas: canvasPane, details: detailsPane,
  };

  return (
    <div className="app">
      {/* ------------------------------------------------------------ top */}
      <a className="skip" href="#workspace">Skip to the workspace</a>

      <header className="toolbar">
        {/* The page needs exactly one h1, and on a tool the product name is
            it. Wrapping a link means the studio has a way back to the site. */}
        <h1 className="brand">
          <a href="/" title="Back to the AlgoStudio overview">
            <img src="/favicon.svg" width="22" height="22" alt="" />
            <span className="brand-text">Algo<span>Studio</span></span>
          </a>
        </h1>

        {/* The way in. It used to be a native <select> of 49 options; now it
            opens a searchable library, and says what is loaded right now. */}
        <button
          type="button"
          className="library-btn"
          onClick={() => setBrowserOpen(true)}
          aria-haspopup="dialog"
          title="Choose an algorithm (Ctrl+K)"
        >
          <Icon name="library" />
          <span className="lb-text">
            <span className="lb-kicker">{plugin ? "Algorithm" : "Library"}</span>
            <span className="lb-name">
              {plugin ? plugin.name : selectedAlgorithm ? "Loading…" : "Your code"}
            </span>
          </span>
          <Icon name="chevron" size={14} />
        </button>

        <button
          className="primary run-btn"
          onClick={doRun}
          disabled={exec.busy || (curated && !selectedAlgorithm)}
          title={selectedAlgorithm && (!editing || curated)
            ? "Run this algorithm again from the start"
            : curated
            ? "This deployment runs the bundled catalogue only — pick an algorithm"
            : runsLocally
              ? "Run your code in this tab (Ctrl+Enter). It is never sent to the server."
              : "Run the code on the left (Ctrl+Enter)"}
        >
          {exec.busy ? <span className="spinner small" aria-hidden="true" /> : <Icon name="play" />}
          {exec.busy
            ? exec.engineStatus && exec.engineStatus.stage !== "ready"
              ? "Preparing…"
              : "Running…"
            : "Run"}
        </button>
        <div className="grow" />

        {/* Only what needs attention. A green "Finished" and an event count on
            every successful run were noise -- success is the normal case, and
            "events" is the engine's word, not the user's. A run that failed,
            timed out or hit its budget still says so, prominently. */}
        <div className="status" aria-live="polite">
          {maximized && (
            <button className="chip-btn on" onClick={() => setMaximized(null)}
                    title="Esc also restores">
              Restore layout
            </button>
          )}
          {bundle && bundle.summary.status !== "ok" && (
            <span className={`badge ${bundle.summary.status}`}>
              {bundle.summary.status === "budget_exceeded"
                ? "Stopped: too many steps"
                : bundle.summary.status === "timeout"
                  ? "Stopped: took too long"
                  : "Ended with an error"}
            </span>
          )}
          {curated && <span className="engine-chip">Catalogue only</span>}
        </div>

        <Popover label="Settings" trigger={<Icon name="settings" size={18} />}>
          <div className="pop-section">
            <div className="pop-title" id="gran-title">Recording detail</div>
            <div role="radiogroup" aria-labelledby="gran-title" className="gran-options">
              {GRANULARITY.map((g) => (
                <label key={g.id} className={`gran-option${granularity === g.id ? " on" : ""}`}>
                  <input
                    type="radio"
                    name="granularity"
                    value={g.id}
                    checked={granularity === g.id}
                    onChange={() => setGranularity(g.id)}
                  />
                  <span className="go-label">{g.label}</span>
                  <span className="go-detail">{g.detail}</span>
                </label>
              ))}
            </div>
            <p className="pop-note">Applies to the next run.</p>
          </div>
        </Popover>

        {/* The studio is a dead end without these: it is served at its own URL,
            so someone who lands here directly has no other route to what the
            project is or what it stores. */}
        <Popover label="Help and shortcuts" trigger={<Icon name="help" size={18} />}>
          <div className="pop-section">
            <div className="pop-title">Keyboard</div>
            <dl className="shortcuts">
              <dt><kbd>Space</kbd></dt><dd>Play or pause</dd>
              <dt><kbd>←</kbd> <kbd>→</kbd></dt><dd>Step back or forward</dd>
              <dt><kbd>Home</kbd> <kbd>End</kbd></dt><dd>Jump to start or end</dd>
              <dt><kbd>Ctrl</kbd> <kbd>K</kbd></dt><dd>Open the library</dd>
              <dt><kbd>Ctrl</kbd> <kbd>Enter</kbd></dt><dd>Run from the editor</dd>
              <dt><kbd>Esc</kbd></dt><dd>Close, or restore a maximized panel</dd>
            </dl>
          </div>
          <nav className="pop-section pop-links" aria-label="Site">
            <a href="/">About AlgoStudio</a>
            <a href="/faq">FAQ</a>
            <a href="/privacy">Privacy</a>
            <a href="/terms">Terms</a>
            <a href="https://github.com/bm-Shreyas05/algostudio" rel="noopener">Source on GitHub</a>
          </nav>
        </Popover>
      </header>

      {/* Only once there is something to play. Before that it was a row of
          greyed-out buttons -- three rows on a phone, a third of the screen --
          offering nothing. */}
      {bundle && (
        <Transport
          step={state.step}
          lastStep={lastStep}
          playing={exec.transport.playing}
          speed={exec.transport.speed}
          stepMode={exec.stepMode}
          enabled={Boolean(bundle)}
          onSeek={exec.seek}
          onStepBack={exec.stepBack}
          onStepForward={exec.stepForward}
          onTogglePlay={() => exec.setTransport((t) => ({ ...t, playing: !t.playing }))}
          onReplay={exec.replay}
          onJumpEnd={() => exec.seek(lastStep)}
          onStepOver={() => exec.jump((tl, st) => tl.stepOver(st))}
          onStepInto={() => exec.jump((tl, st) => tl.stepInto(st))}
          onStepOut={() => exec.jump((tl, st) => tl.stepOut(st))}
          onSpeed={(speed) => exec.setTransport((t) => ({ ...t, speed }))}
          onStepMode={exec.setStepMode}
        />
      )}

      {plugin && (
        // What it does and what it costs. The name is already in the library
        // button directly above; the "annotated / semantics inferred" badge
        // described how the plugin was written, which no learner asked.
        <div className="algo-strip">
          <span className="muted">{plugin.description}</span>
          {plugin.complexity && (
            <span className="cx" title="Time and extra space this algorithm needs">
              {plugin.complexity.time} time · {plugin.complexity.space} space
            </span>
          )}
        </div>
      )}

      {/* ------------------------------------------------------- capability */}
      {bundle && issues.length > 0 && (
        <div className={`banner ${issues.some((i) => i.severity === "unsupported") ? "bad" : "warn"}`}>
          {issues.slice(0, 3).map((issue, i) => (
            <span key={i}>line {issue.line}: {issue.message}</span>
          ))}
          {issues.length > 3 && <span>+{issues.length - 3} more</span>}
        </div>
      )}
      {exec.error && <div className="banner bad"><span>{exec.error}</span></div>}
      {exec.engineStatus && exec.engineStatus.stage !== "ready" && exec.busy && (
        <div className="banner">
          <span>
            <strong>{exec.engineStatus.message}</strong>{" "}
            This happens once — afterwards your code runs instantly, in this
            tab, and is never sent to the server.
          </span>
        </div>
      )}

      {bundle?.summary.error && (
        <div className="banner bad">
          <span>
            {bundle.summary.error.type}: {bundle.summary.error.message}
            {bundle.summary.error.line ? ` (line ${bundle.summary.error.line})` : ""}
            {" — the trace is still fully navigable."}
          </span>
        </div>
      )}

      {/* ----------------------------------------------------------- body */}
      {isMobile ? (
        <>
          <div id="workspace" className="pane-tabs" role="tablist" aria-label="Panels">
            {MOBILE_PANES.map(([id, label]) => (
              <button
                key={id}
                role="tab"
                id={`tab-${id}`}
                aria-selected={mobilePane === id}
                aria-controls={`panel-${id}`}
                className={mobilePane === id ? "on" : ""}
                onClick={() => setMobilePane(id)}
              >
                {label}
              </button>
            ))}
          </div>
          <div
            className="workspace mobile"
            role="tabpanel"
            id={`panel-${mobilePane}`}
            aria-labelledby={`tab-${mobilePane}`}
          >
            {PANES[mobilePane]}
          </div>
        </>
      ) : maximized ? (
        <div id="workspace" className="workspace maximized">{PANES[maximized]}</div>
      ) : (
        // v3: two columns. Code above the details of the run on the left, the
        // visualization full-height on the right. A new storage key, because
        // a v2 layout saved three column widths and there are now two.
        <Split
          id="workspace"
          direction="row"
          storageKey="algostudio.layout.v3.cols"
          initial={[40, 60]}
          minPx={300}
          className="workspace"
        >
          <Split
            direction="column"
            storageKey="algostudio.layout.v3.left"
            initial={[58, 42]}
            minPx={140}
          >
            {sourcePane}
            {detailsPane}
          </Split>
          {canvasPane}
        </Split>
      )}

      <AlgorithmBrowser
        open={browserOpen}
        algorithms={algorithms}
        currentId={selectedAlgorithm}
        onClose={() => setBrowserOpen(false)}
        onPick={pickAlgorithm}
        onWriteOwn={writeOwn}
      />
    </div>
  );
}
