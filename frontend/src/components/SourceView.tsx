import { useEffect, useMemo, useRef } from "react";
import type { CapabilityIssue, ExecutionState } from "../api/types";
import { highlightLines } from "../lib/highlight";
import { CodeEditor } from "./CodeEditor";

interface Props {
  source: string;
  editable: boolean;
  onChange: (source: string) => void;
  state: ExecutionState;
  lineHits: Record<string, number>;
  issues: CapabilityIssue[];
  breakpoints: Set<number>;
  onToggleBreakpoint: (line: number) => void;
  branchLine: number | null;
  /** Ctrl/Cmd+Enter from inside the editor. */
  onRun?: () => void;
  focusRequested?: boolean;
  onFocusHandled?: () => void;
}

/**
 * Editor plus execution overlay.
 *
 * Executed lines are tinted by hit count -- a cheap heat map that makes dead
 * branches obvious at a glance, which is usually the first thing a student
 * needs to see in a program that "doesn't work".
 */
export function SourceView({
  source, editable, onChange, state, lineHits, issues, breakpoints,
  onToggleBreakpoint, branchLine, onRun, focusRequested, onFocusHandled,
}: Props) {
  const lines = useMemo(() => source.split("\n"), [source]);
  // Tokenized as a whole, then split, so a multi-line string stays a string.
  const highlighted = useMemo(() => highlightLines(source), [source]);
  // Nothing is "current" once the program has ended; its last location is
  // usually the `def` line of the function that returned last.
  const currentLine = state.finished_reason ? 0 : state.current_loc?.line ?? 0;
  const activeRef = useRef<HTMLDivElement | null>(null);

  const maxHits = useMemo(
    () => Math.max(1, ...Object.values(lineHits ?? {})),
    [lineHits],
  );
  const issueByLine = useMemo(() => {
    const map = new Map<number, CapabilityIssue>();
    for (const issue of issues) if (!map.has(issue.line)) map.set(issue.line, issue);
    return map;
  }, [issues]);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ block: "nearest" });
  }, [currentLine]);

  if (editable) {
    return (
      <CodeEditor
        value={source}
        onChange={onChange}
        onRun={onRun}
        focusRequested={focusRequested}
        onFocusHandled={onFocusHandled}
      />
    );
  }

  return (
    <div className="source-view">
      {lines.map((_line, i) => {
        const number = i + 1;
        const hits = lineHits?.[String(number)] ?? 0;
        const issue = issueByLine.get(number);
        const isCurrent = number === currentLine;
        return (
          <div
            key={number}
            ref={isCurrent ? activeRef : undefined}
            className={
              "source-line" +
              (isCurrent ? " current" : "") +
              (number === branchLine ? " branch" : "") +
              (hits ? " executed" : "")
            }
            style={hits ? { ["--heat" as any]: `${(hits / maxHits) * 0.22}` } : undefined}
          >
            <span
              className={`gutter${breakpoints.has(number) ? " breakpoint" : ""}`}
              onClick={() => onToggleBreakpoint(number)}
              title={
                issue
                  ? `${issue.severity}: ${issue.message}`
                  : hits
                    ? `Ran ${hits} time${hits === 1 ? "" : "s"} — click to add a breakpoint`
                    : "Click to add a breakpoint"
              }
            >
              {number}
            </span>
            {/* The execution count used to be a second column of numbers
                beside the line numbers -- two unlabelled columns of digits,
                which read as a rendering fault. The tint behind each line
                already shows which ran most; the exact count is in the line
                number's tooltip. */}
            <code
              className={issue ? `issue ${issue.severity}` : undefined}
              // Built only from our own token classes and escaped text.
              dangerouslySetInnerHTML={{ __html: highlighted[i] || " " }}
            />
          </div>
        );
      })}
    </div>
  );
}
