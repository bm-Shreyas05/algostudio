import { useEffect, useMemo, useRef } from "react";
import type { CapabilityIssue, ExecutionState } from "../api/types";

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
  onToggleBreakpoint, branchLine,
}: Props) {
  const lines = useMemo(() => source.split("\n"), [source]);
  const currentLine = state.current_loc?.line ?? 0;
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
      <textarea
        className="source-editor"
        spellCheck={false}
        value={source}
        onChange={(e) => onChange(e.target.value)}
        placeholder="# Write Python here, then press Run"
      />
    );
  }

  return (
    <div className="source-view">
      {lines.map((text, i) => {
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
                    ? `${hits} executions — click to toggle breakpoint`
                    : "click to toggle breakpoint"
              }
            >
              {number}
            </span>
            <span className="hits">{hits || ""}</span>
            <code className={issue ? `issue ${issue.severity}` : undefined}>
              {text || " "}
            </code>
          </div>
        );
      })}
    </div>
  );
}
