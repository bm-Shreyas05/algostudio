import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api/client";
import type { AlgorithmPlugin, EncodedValue } from "./api/types";
import { AIPanel } from "./components/AIPanel";
import {
  AnalyticsPanel, CallStackPanel, ConsolePanel, TimelinePanel, VariablesPanel,
} from "./components/Panels";
import { SourceView } from "./components/SourceView";
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

  useEffect(() => {
    api.algorithms().then((r) => setAlgorithms(r.algorithms)).catch(() => undefined);
    api.health().then(setHealth).catch(() => undefined);
  }, []);

  const { bundle, state, timeline } = exec;

  /* ---- previous frame locals, for the change highlight ------------------ */
  const previousLocals = useMemo<Record<string, EncodedValue>>(() => {
    if (!timeline || state.step <= 0) return {};
    const before = timeline.stateAt(state.step - 1);
    return before.frames[before.frames.length - 1]?.locals ?? {};
  }, [timeline, state.step]);

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
      if (editing || (e.target as HTMLElement)?.tagName === "INPUT") return;
      if (e.key === "ArrowRight") { e.preventDefault(); exec.stepForward(); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); exec.stepBack(); }
      else if (e.key === " ") {
        e.preventDefault();
        exec.setTransport((t) => ({ ...t, playing: !t.playing }));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [editing, exec]);

  const inspectVariable = useCallback((name: string) => {
    setFocusVariable(name);
    if (!timeline) return;
    const target = timeline.previousWrite(state.step, name);
    if (target !== null) exec.seek(target);
  }, [timeline, state.step, exec]);

  // Depends on `state`, not `state.heap`: the reducer mutates the heap in place
  // for speed, so its identity is stable across a forward step and a memo keyed
  // on it would never recompute. The state wrapper is fresh on every publish.
  const plans = useMemo(() => {
    if (!bundle) return [];
    return bundle.views
      .map((v) => (pinned[v.ref] ? { ...v, view: pinned[v.ref] } : v))
      .filter((v) => state.heap[v.ref])
      .slice(0, 4);
  }, [bundle, pinned, state]);

  const issues = bundle?.summary.capability_report.issues ?? [];
  const lastStep = timeline?.lastStep ?? 0;

  return (
    <div className="app">
      {/* ------------------------------------------------------------ top */}
      <header className="toolbar">
        <div className="brand">
          Algo<span>Studio</span>
        </div>

        <select
          value={selectedAlgorithm}
          onChange={(e) => loadAlgorithm(e.target.value)}
          title="Packaged algorithms run through exactly the same pipeline as your own code"
        >
          <option value="">— your own code —</option>
          {algorithms.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}{a.annotated ? "" : "  (un-annotated)"}
            </option>
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
        <button onClick={() => setEditing((v) => !v)} disabled={!bundle}>
          {editing ? "Trace" : "Edit"}
        </button>

        <div className="transport">
          <button onClick={() => exec.seek(0)} title="Restart (no re-execution)">⏮</button>
          <button onClick={() => exec.jump((tl, s) => tl.stepOut(s))} title="Step out">⤴</button>
          <button onClick={exec.stepBack} title="Step back (←)">◀</button>
          <button
            className="play"
            onClick={() => exec.setTransport((t) => ({ ...t, playing: !t.playing }))}
            title="Play / pause (space)"
          >
            {exec.transport.playing ? "⏸" : "▶"}
          </button>
          <button onClick={exec.stepForward} title="Step forward (→)">▶</button>
          <button onClick={() => exec.jump((tl, s) => tl.stepOver(s))} title="Step over">⤵</button>
          <button onClick={() => exec.jump((tl, s) => tl.stepInto(s))} title="Step into">↘</button>
          <button onClick={() => exec.seek(lastStep)} title="Jump to end">⏭</button>
          <input
            type="range" min={5} max={120} value={exec.transport.speed}
            onChange={(e) => exec.setTransport((t) => ({ ...t, speed: +e.target.value }))}
            title="playback speed"
          />
        </div>

        <div className="grow" />
        <div className="status">
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

      {/* ------------------------------------------------------- capability */}
      {bundle && issues.length > 0 && (
        <div className={`banner ${issues.some((i) => i.severity === "unsupported") ? "bad" : "warn"}`}>
          {issues.slice(0, 3).map((issue, i) => (
            <span key={i}>
              line {issue.line}: {issue.message}
            </span>
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

      {/* ----------------------------------------------------------- main */}
      <main className="grid">
        <section className="pane source">
          <div className="pane-head">
            <span>Source</span>
            {bundle && <span className="muted">step {state.step} / {lastStep}</span>}
          </div>
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

        <section className="pane canvas">
          <div className="pane-head">
            <span>Visualization</span>
            <span className="muted">views chosen from runtime structure</span>
          </div>
          <div className="canvas-body">
            {!bundle && <div className="empty pad">Run a program to see its execution.</div>}
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
                        onChange={(e) =>
                          setPinned((p) => ({ ...p, [plan.ref]: e.target.value }))
                        }
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
                    object={state.heap[plan.ref]}
                    heap={state.heap}
                    annotations={annotationsFor(annotations, plan.ref)}
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

        <section className="pane inspector">
          <div className="pane-head tabs">
            {(["variables", "callstack", "calltree"] as RightTab[]).map((tab) => (
              <button key={tab} className={rightTab === tab ? "on" : ""}
                      onClick={() => setRightTab(tab)}>
                {tab === "callstack" ? "call stack" : tab}
              </button>
            ))}
          </div>
          {rightTab === "variables" && (
            <VariablesPanel
              state={state}
              previousLocals={previousLocals}
              onInspect={inspectVariable}
            />
          )}
          {rightTab === "callstack" && <CallStackPanel state={state} />}
          {rightTab === "calltree" && (
            <div className="panel-body"><CallTreeView state={state} /></div>
          )}
        </section>
      </main>

      {/* --------------------------------------------------------- bottom */}
      <footer className="bottom">
        <div className="scrubber">
          <input
            type="range"
            min={0}
            max={Math.max(0, lastStep)}
            value={Math.max(0, state.step)}
            onChange={(e) => exec.seek(+e.target.value)}
            disabled={!bundle}
          />
        </div>
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
      </footer>
    </div>
  );
}
