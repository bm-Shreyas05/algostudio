import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { AlgorithmPlugin, EncodedValue } from "./api/types";
import type { ChangedBinding } from "./components/Panels";
import { AIPanel } from "./components/AIPanel";
import { FocusStrip } from "./components/FocusStrip";
import {
  AnalyticsPanel, CallStackPanel, ConsolePanel, TimelinePanel, VariablesPanel,
} from "./components/Panels";
import { SourceView } from "./components/SourceView";
import { PaneHead, Split } from "./components/Split";
import { Transport } from "./components/Transport";
import { liveAnnotations } from "./engine/reducer";
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

  useEffect(() => {
    api.algorithms().then((r) => setAlgorithms(r.algorithms)).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const { bundle, state, timeline } = exec;

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
    const result = await exec.run(source, granularity);
    if (result) setEditing(false);
  }, [exec, source, granularity]);

  const loadAlgorithm = useCallback(async (id: string) => {
    setSelectedAlgorithm(id);
    if (!id) return;
    const plugin = await api.algorithm(id);
    setSource(plugin.source ?? "");
    const inputs = Object.fromEntries(plugin.inputs.map((f) => [f.name, f.default]));
    const result = await exec.runAlgorithm(id, inputs, granularity);
    if (result) setEditing(false);
  }, [exec, granularity]);

  /* ---- keyboard transport ---------------------------------------------- */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (editing || tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "ArrowRight") { e.preventDefault(); exec.stepForward(); }
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
  }, [editing, exec, maximized]);

  const inspectVariable = useCallback((name: string) => {
    setFocusVariable(name);
    if (!timeline) return;
    const target = timeline.previousWrite(state.step, name);
    if (target !== null) exec.seek(target);
  }, [timeline, state.step, exec]);

  const plans = useMemo(() => {
    if (!bundle) return [];
    return bundle.views
      .map((v) => (pinned[v.ref] ? { ...v, view: pinned[v.ref] } : v))
      // Synthetic plans (strings, scalar frames) are not heap objects; they
      // bring their own record in props.
      .filter((v) => state.heap[v.ref] || v.props?.record)
      .slice(0, 6);
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
        editable={editing}
        onChange={setSource}
        state={state}
        lineHits={bundle?.analytics.line_hits ?? {}}
        issues={issues}
        breakpoints={exec.breakpoints}
        onToggleBreakpoint={exec.toggleBreakpoint}
        branchLine={branchLine}
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
        {!bundle && (
          <div className="canvas-empty">
            <h3>Nothing recorded yet</h3>
            <p>
              Press <strong>▶ Run</strong> to execute the code on the left, or pick
              an algorithm from the menu above. Playback starts automatically.
            </p>
            <ul>
              <li>Views are chosen from the shape of the data at runtime — an
                  adjacency map becomes a graph, a list of numbers becomes an array.</li>
              <li><kbd>←</kbd> <kbd>→</kbd> step, <kbd>space</kbd> plays,
                  <kbd>Esc</kbd> restores a maximized panel.</li>
              <li>Drag any divider to resize, or press <strong>⛶</strong> on a panel
                  to give it the whole window.</li>
            </ul>
          </div>
        )}
        {plans.map((plan) => {
          const View = resolveView(plan.view);
          return (
            <div key={plan.ref} className="view-card">
              <div className="view-head">
                <strong>{plan.name || plan.ref}</strong>
                <span className="muted" title={plan.reason}>
                  {VIEW_LABELS[plan.view] ?? plan.view} · {plan.score.toFixed(2)}
                </span>
                {plan.alternatives.length > 0 && (
                  <select
                    value={plan.view}
                    onChange={(e) => setPinned((p) => ({ ...p, [plan.ref]: e.target.value }))}
                    title="view as…"
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
      <header className="toolbar">
        <div className="brand">Algo<span>Studio</span></div>

        <select
          value={selectedAlgorithm}
          onChange={(e) => loadAlgorithm(e.target.value)}
          title="Packaged algorithms run through exactly the same pipeline as your own code"
        >
          <option value="">— your own code —</option>
          {Object.entries(
            algorithms.reduce<Record<string, AlgorithmPlugin[]>>((groups, a) => {
              (groups[a.category] ??= []).push(a);
              return groups;
            }, {}),
          )
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([category, items]) => (
              <optgroup key={category} label={category}>
                {items.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.name}
                    {a.complexity ? `  —  ${a.complexity.time}` : ""}
                  </option>
                ))}
              </optgroup>
            ))}
        </select>

        <select value={granularity} onChange={(e) => setGranularity(e.target.value)}
                title="How finely execution is instrumented">
          <option value="minimal">minimal</option>
          <option value="standard">standard</option>
          <option value="verbose">verbose</option>
        </select>

        <button className="primary" onClick={doRun} disabled={exec.busy}>
          {exec.busy ? "Running…" : "▶ Run"}
        </button>
        <button
          onClick={() => setEditing((v) => !v)}
          disabled={!bundle}
          title={editing ? "Show the recorded trace" : "Go back to editing the source"}
        >
          {editing ? "View trace" : "Edit code"}
        </button>

        <div className="grow" />
        <div className="status">
          {maximized && (
            <button className="chip-btn on" onClick={() => setMaximized(null)}
                    title="Esc also restores">
              ⛶ {maximized} — restore
            </button>
          )}
          {bundle && (
            <>
              <span className={`badge ${bundle.summary.status}`}>{bundle.summary.status}</span>
              <span>{bundle.summary.event_count} events</span>
              {bundle.summary.lifters && <span title="semantic lifting is on">lifting on</span>}
            </>
          )}
          {health && <span title={`sandbox: ${health.sandbox_mode}`}>{health.sandbox_mode}</span>}
        </div>
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
      {maximized ? (
        <div className="workspace maximized">{PANES[maximized]}</div>
      ) : (
        <Split
          direction="column"
          storageKey="algostudio.layout.v1.rows"
          initial={[64, 36]}
          minPx={110}
          className="workspace"
        >
          <Split
            direction="row"
            storageKey="algostudio.layout.v1.cols"
            initial={[30, 44, 26]}
            minPx={160}
          >
            {sourcePane}
            {canvasPane}
            {inspectorPane}
          </Split>
          {bottomPane}
        </Split>
      )}
    </div>
  );
}
