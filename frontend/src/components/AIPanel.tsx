import { useState } from "react";
import { api } from "../api/client";
import type { AIAnswer } from "../api/types";

const MODES: { id: string; label: string; needsVariable?: boolean }[] = [
  { id: "explain_line", label: "Explain this line" },
  { id: "why_value", label: "Why this value?", needsVariable: true },
  { id: "why_branch", label: "Why this branch?" },
  { id: "why_called", label: "Why was this called?" },
  { id: "what_changed", label: "What changed?" },
  { id: "explain_algorithm", label: "Explain the algorithm" },
  { id: "complexity", label: "Time complexity" },
  { id: "simpler", label: "Simpler please" },
  { id: "quiz", label: "Quiz me" },
];

/**
 * The AI panel shows the grounding report alongside the answer.
 *
 * A claim the verifier confirmed against the recording is marked; one it could
 * not check is marked differently; one that contradicts the recording is called
 * out. The point is that the student can see which parts are load-bearing.
 */
export function AIPanel({
  executionId, step, focusVariable,
}: {
  executionId: string | null;
  step: number;
  focusVariable: string;
}) {
  const [mode, setMode] = useState("explain_line");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AIAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const ask = async (useMode = mode) => {
    if (!executionId) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.ask(executionId, {
        step,
        mode: useMode,
        question,
        focus: focusVariable ? { variable: focusVariable } : {},
      });
      setAnswer(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const grounding = answer?.grounding;

  return (
    <div className="panel-body ai">
      <div className="ai-modes">
        {MODES.map((m) => (
          <button
            key={m.id}
            className={`chip-btn${mode === m.id ? " on" : ""}`}
            onClick={() => { setMode(m.id); void ask(m.id); }}
            disabled={!executionId || busy}
            title={m.needsVariable ? `uses the selected variable${focusVariable ? `: ${focusVariable}` : ""}` : undefined}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="ai-ask">
        <input
          placeholder={
            focusVariable
              ? `ask about step ${step} (focused on ${focusVariable})…`
              : `ask about step ${step}…`
          }
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          disabled={!executionId}
        />
        <button onClick={() => ask()} disabled={!executionId || busy}>
          {busy ? "…" : "Ask"}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {answer && (
        <div className="ai-answer">
          <p>{answer.answer}</p>
          {answer.notice && <div className="notice">{answer.notice}</div>}
          {grounding && grounding.claims.length > 0 && (
            <div className="grounding">
              <div className="grounding-head">
                Grounding: {grounding.verified} verified
                {grounding.unverified ? `, ${grounding.unverified} unchecked` : ""}
                {grounding.contradicted ? `, ${grounding.contradicted} contradicted` : ""}
              </div>
              <ul>
                {grounding.claims.map((claim, i) => (
                  <li
                    key={i}
                    className={
                      claim.contradicted ? "bad" : claim.verified ? "good" : "unknown"
                    }
                  >
                    <code>{claim.text}</code>
                    {claim.contradicted && <em> — trace says {claim.actual}</em>}
                  </li>
                ))}
              </ul>
              <div className="muted small">{grounding.note}</div>
            </div>
          )}
          <div className="muted small">
            {answer.provider}
            {answer.model ? ` · ${answer.model}` : ""}
            {answer.cached ? " · cached" : ""}
          </div>
        </div>
      )}
    </div>
  );
}
