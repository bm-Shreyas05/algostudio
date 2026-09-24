import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { AIAnswer } from "../api/types";
import { loadedBrowserEngine } from "../engine/browserEngine";

interface Mode {
  id: string;
  label: string;
  /** Needs a variable chosen in the Variables tab first. */
  needsVariable?: boolean;
}

/**
 * Four questions, not nine.
 *
 * The tutor used to offer nine modes. On a deployment with no language model
 * most of them were the same template in different words: "Simpler please"
 * literally called "Explain this line", "What changed?" repeated the narration
 * above the canvas, and "Time complexity" repeated the Stats tab. These four
 * each answer something nothing else on screen does.
 */
const MODES: Mode[] = [
  { id: "explain_line", label: "Explain this step" },
  { id: "why_value", label: "Why this value?", needsVariable: true },
  { id: "explain_algorithm", label: "What is this program doing?" },
  { id: "quiz", label: "Quiz me" },
];

/**
 * Answers about the step you are on, checked against the recording.
 *
 * A run of your own code exists only in this tab, so questions about it are
 * answered here by the same explainer the server uses, rather than being sent
 * to a server that has never seen the run. (They used to be, and got a 404.)
 */
export function AIPanel({
  executionId, step, focusVariable, local, llmAvailable,
}: {
  executionId: string | null;
  step: number;
  focusVariable: string;
  /** The run happened in this tab, not on the server. */
  local: boolean;
  /** A language model is configured; otherwise answers come from a template. */
  llmAvailable: boolean;
}) {
  const [mode, setMode] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AIAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showChecks, setShowChecks] = useState(false);

  // An answer is about one step; once the step moves it is about the past.
  useEffect(() => {
    setAnswer(null);
    setMode(null);
  }, [step, executionId]);

  const ask = async (useMode: string) => {
    if (!executionId) return;
    setMode(useMode);
    setBusy(true);
    setError("");
    try {
      if (local) {
        const engine = await loadedBrowserEngine();
        if (!engine) throw new Error("run the program first");
        setAnswer(engine.ask(step, useMode, question, focusVariable));
      } else {
        setAnswer(await api.ask(executionId, {
          step,
          mode: useMode,
          question,
          focus: focusVariable ? { variable: focusVariable } : {},
        }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!executionId) {
    return (
      <div className="panel-body ai">
        <p className="tab-empty">Run something first — then ask about any step of it.</p>
      </div>
    );
  }

  const grounding = answer?.grounding;
  const checked = grounding ? grounding.verified : 0;
  const contradicted = grounding ? grounding.contradicted : 0;

  return (
    <div className="panel-body ai">
      <p className="ai-intro">Ask about step <strong>{step}</strong>:</p>
      <div className="ai-modes">
        {MODES.map((m) => {
          const blocked = m.needsVariable && !focusVariable;
          return (
            <button
              key={m.id}
              className={mode === m.id ? "on" : ""}
              onClick={() => ask(m.id)}
              disabled={busy || blocked}
              title={blocked ? "Click a variable name in the Variables tab first" : undefined}
            >
              {m.id === "why_value" && focusVariable ? `Why is ${focusVariable} this value?` : m.label}
            </button>
          );
        })}
      </div>
      {!focusVariable && (
        <p className="ai-hint">
          Tip: click a variable's name in the <em>Variables</em> tab to ask why it has
          the value it does.
        </p>
      )}

      {/* A free-text box implies you can ask anything. Without a language model
          the answer is chosen by the buttons above, whatever is typed, so the
          box would be a promise the tutor cannot keep. */}
      {llmAvailable && !local && (
        <div className="ai-ask">
          <input
            aria-label="Ask a question about this step"
            placeholder="Or ask your own question…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask(mode ?? "explain_line")}
          />
          <button onClick={() => ask(mode ?? "explain_line")} disabled={busy}>Ask</button>
        </div>
      )}

      {error && <div className="error">{error}</div>}
      {busy && <p className="ai-busy">Thinking…</p>}

      {answer && !busy && (
        <div className="ai-answer">
          <p>{answer.answer}</p>
          {grounding && grounding.claims.length > 0 && (
            <div className="ai-checks">
              <button
                type="button"
                className="linkish"
                aria-expanded={showChecks}
                onClick={() => setShowChecks((v) => !v)}
              >
                {contradicted
                  ? `⚠ ${contradicted} statement${contradicted > 1 ? "s" : ""} disagree with the recording`
                  : checked
                    ? `✓ ${checked} fact${checked > 1 ? "s" : ""} checked against the recording`
                    : "How was this checked?"}
              </button>
              {showChecks && (
                <ul className="grounding">
                  {grounding.claims.map((claim, i) => (
                    <li
                      key={i}
                      className={claim.contradicted ? "bad" : claim.verified ? "good" : "unknown"}
                    >
                      <code>{claim.text}</code>
                      {claim.contradicted && <em> — the recording says {claim.actual}</em>}
                      {!claim.contradicted && !claim.verified && <span className="muted"> — not checkable</span>}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
