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
  AnalyticsPanel, CallStackPanel, ConsolePanel, TimelinePanel, VariablesPanel,
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

type RightTab = "variables" | "callstack" | "calltree";
type BottomTab = "timeline" | "console" | "analytics" | "ai";
type PaneId = "source" | "canvas" | "inspector" | "bottom";

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
function sizeLabel(obj: HeapObject | undefined): string {
  if (!obj || typeof obj.n !== "number") return "";
  if (!obj.items && !obj.entries) return "";
  return ` · ${obj.n} ${obj.n === 1 ? "item" : "items"}`;
}

/** Tab order on narrow screens: what you look at most, first. */
const MOBILE_PANES: [PaneId, string][] = [
  ["canvas", "Visual"],
  ["source", "Code"],
  ["inspector", "Data"],
  ["bottom", "Timeline"],
];

export default function App() {
  const exec = useExecution();
  const [source, setSource] = useState(STARTER);
  const [editing, setEditing] = useState(true);
  const [granularity, setGranularity] = useState("standard");
  const [algorithms, setAlgorithms] = useState<AlgorithmPlugin[]>([]);
  const [selectedAlgorithm, setSelectedAlgorithm] = useState("");
  const [rightTab, setRightTab] = useState<RightTab>("variables");
  const [bottomTab, setBottomTab] = useState<BottomTab>("timeline");
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

  const annotations = useMemo(() => liveAnnotations(state), [state]);

  const branchLine = useMemo(() => {
    if (!bundle || state.step < 0) return null;
    for (let i = state.step; i >= Math.max(0, state.step - 6); i--) {
      const ev = bundle.events[i];
      if (ev?.type === "BRANCH_TAKEN") return ev.loc?.line ?? null;
    }
    return null;
  }, [bundle, state.step]);

  /* ---- run -------------------------------------------------------------- */
  const doRun = useCallback(async () => {
    setSelectedAlgorithm("");
    // Where this executes is the whole security story: runsLocally means the
    // source never leaves the tab.
    const result = runsLocally
      ? await exec.runLocal(source, granularity)
      : await exec.run(source, granularity);
    if (result) setEditing(false);
  }, [exec, source, granularity, runsLocally]);

  const loadAlgorithm = useCallback(async (id: string) => {
    setSelectedAlgorithm(id);
    if (!id) return;
    const plugin = await api.algorithm(id);
    setSource(plugin.source ?? "");
    const inputs = Object.fromEntries(plugin.inputs.map((f) => [f.name, f.default]));
    const result = await exec.runAlgorithm(id, inputs, granularity);
    if (result) setEditing(false);
  }, [exec, granularity]);

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
        title="Source"
        extra={bundle && <span className="muted">step {state.step} / {lastStep}</span>}
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
        extra={<span className="muted">views chosen from runtime structure</span>}
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
              Each of these lands on a different kind of picture. None of them is
              drawn by hand — the view is worked out from the shape of the data
              while the program runs.
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

            {runsLocally && (
              <p className="ce-note">
                <Icon name="lock" size={14} />
                Code you write runs inside this tab. It is never uploaded, and the
                server is never asked to execute it.
              </p>
            )}
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
                  {sizeLabel(state.heap[plan.ref])}
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
              <strong>call tree</strong>
              <span className="muted">derived from function events</span>
            </div>
            <CallTreeView state={state} />
          </div>
        )}
      </div>
    </section>
  );

  const inspectorPane = (
    <section className="pane inspector">
      <div className="pane-head tabs">
        {(["variables", "callstack", "calltree"] as RightTab[]).map((tab) => (
          <button key={tab} className={rightTab === tab ? "on" : ""}
                  onClick={() => setRightTab(tab)}>
            {tab === "callstack" ? "call stack" : tab}
          </button>
        ))}
        <span className="grow" />
        <button className="pane-btn" onClick={toggleMax("inspector")}
                title={maximized === "inspector" ? "restore layout" : "maximize this panel"}>
          {maximized === "inspector" ? "🗗" : "⛶"}
        </button>
      </div>
      {rightTab === "variables" && (
        <VariablesPanel state={state} changed={changed} onInspect={inspectVariable} />
      )}
      {rightTab === "callstack" && <CallStackPanel state={state} />}
      {rightTab === "calltree" && (
        <div className="panel-body"><CallTreeView state={state} /></div>
      )}
    </section>
  );

  const bottomPane = (
    <section className="pane bottom">
      <div className="pane-head tabs">
        {(["timeline", "console", "analytics", "ai"] as BottomTab[]).map((tab) => (
          <button key={tab} className={bottomTab === tab ? "on" : ""}
                  onClick={() => setBottomTab(tab)}>
            {tab === "ai" ? "AI tutor" : tab}
          </button>
        ))}
        {focusVariable && bottomTab === "ai" && (
          <span className="muted">focused on {focusVariable}</span>
        )}
        <span className="grow" />
        <button className="pane-btn" onClick={toggleMax("bottom")}
                title={maximized === "bottom" ? "restore layout" : "maximize this panel"}>
          {maximized === "bottom" ? "🗗" : "⛶"}
        </button>
      </div>
      <div className="bottom-body">
        {bottomTab === "timeline" && bundle && (
          <TimelinePanel events={bundle.events} step={state.step} onSeek={exec.seek} />
        )}
        {bottomTab === "console" && <ConsolePanel state={state} />}
        {bottomTab === "analytics" && bundle && (
          <AnalyticsPanel analytics={bundle.analytics} state={state} />
        )}
        {bottomTab === "ai" && (
          <AIPanel
            executionId={bundle?.summary.execution_id ?? null}
            step={state.step}
            focusVariable={focusVariable}
          />
        )}
        {!bundle && bottomTab !== "ai" && bottomTab !== "console" && (
          <div className="empty pad">Nothing recorded yet.</div>
        )}
      </div>
    </section>
  );

  const PANES: Record<PaneId, React.ReactNode> = {
    source: sourcePane, canvas: canvasPane, inspector: inspectorPane, bottom: bottomPane,
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
          disabled={exec.busy || curated}
          title={curated
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
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setEditing((v) => !v)}
          disabled={!bundle || curated}
          title={editing ? "Show the recorded trace" : "Go back to editing the source"}
        >
          <Icon name="code" />
          <span className="hide-narrow">{editing ? "View trace" : "Edit code"}</span>
        </button>

        <div className="grow" />

        <div className="status" aria-live="polite">
          {maximized && (
            <button className="chip-btn on" onClick={() => setMaximized(null)}
                    title="Esc also restores">
              Restore layout
            </button>
          )}
          {bundle && (
            <span className="run-summary">
              <span className={`badge ${bundle.summary.status}`}>
                {bundle.summary.status === "ok" ? "Finished" : bundle.summary.status.replace("_", " ")}
              </span>
              <span className="hide-narrow">
                {bundle.summary.event_count.toLocaleString()} events
              </span>
            </span>
          )}
          {health && (
            <span
              className={`engine-chip${runsLocally ? " local" : ""}`}
              title={
                runsLocally
                  ? "Your code runs in this tab and is never sent to the server"
                  : `sandbox: ${health.sandbox_mode}`
              }
            >
              {runsLocally && <Icon name="lock" size={13} />}
              {runsLocally
                ? "Runs in your browser"
                : curated
                  ? "Catalogue only"
                  : `${health.sandbox_mode} sandbox`}
            </span>
          )}
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

      {plugin && (
        <div className="algo-strip">
          <strong>{plugin.name}</strong>
          <span className="muted">{plugin.description}</span>
          {plugin.complexity && (
            <span className="cx" title="as stated by the plugin author">
              {plugin.complexity.time} time · {plugin.complexity.space} space
            </span>
          )}
          <span
            className={`origin-badge ${plugin.annotated ? "annotated" : "inferred"}`}
            title={
              plugin.annotated
                ? "This source calls the algo.* API, so its swaps/compares/visits are declared explicitly."
                : "This source has no annotations. Its swaps, comparisons and visits are recovered from the raw event stream by the lifters."
            }
          >
            {plugin.annotated ? "annotated" : "semantics inferred"}
          </span>
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
        // v2: the redesign gives the visualization the most room by default.
        // Saved v1 layouts are left alone rather than migrated -- they were
        // sized for the old chrome, and applying them would hide the change.
        <Split
          id="workspace"
          direction="column"
          storageKey="algostudio.layout.v2.rows"
          initial={[70, 30]}
          minPx={120}
          className="workspace"
        >
          <Split
            direction="row"
            storageKey="algostudio.layout.v2.cols"
            initial={[28, 50, 22]}
            minPx={180}
          >
            {sourcePane}
            {canvasPane}
            {inspectorPane}
          </Split>
          {bottomPane}
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
