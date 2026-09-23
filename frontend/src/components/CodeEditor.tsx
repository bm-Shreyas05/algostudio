import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { highlightHtml } from "../lib/highlight";

interface Props {
  value: string;
  onChange: (value: string) => void;
  /** Called on Ctrl/Cmd+Enter: the shortcut every playground uses for Run. */
  onRun?: () => void;
  label?: string;
}

const INDENT = "    ";

/**
 * A code editor made of a transparent textarea over a highlighted <pre>.
 *
 * The classic technique, chosen over an editor library to keep this app's one
 * dependency (React). The textarea does all the real work -- selection, IME,
 * undo, clipboard, accessibility -- and is simply invisible; the <pre> behind it
 * draws the same text in colour. The two must share font, size, line height,
 * padding and wrapping exactly, and they scroll together.
 *
 * Tab indents, because in a Python editor that is what Tab has to mean. That
 * is a keyboard trap unless there is a way out (WCAG 2.1.2), so Escape releases
 * it: after Escape, the next Tab moves focus on as usual. The editor says so in
 * its accessible description rather than leaving it to be discovered.
 */
export function CodeEditor({ value, onChange, onRun, label = "Python source" }: Props) {
  const textRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const gutterRef = useRef<HTMLDivElement>(null);
  const [tabTrapped, setTabTrapped] = useState(true);

  // A trailing newline in a <pre> is not rendered, so the last line of the
  // overlay would be one line short of the textarea and the caret would drift.
  const html = useMemo(() => highlightHtml(value) + "\n", [value]);
  const lineCount = useMemo(() => value.split("\n").length, [value]);

  const syncScroll = useCallback(() => {
    const t = textRef.current;
    if (!t) return;
    if (preRef.current) {
      preRef.current.scrollTop = t.scrollTop;
      preRef.current.scrollLeft = t.scrollLeft;
    }
    if (gutterRef.current) gutterRef.current.scrollTop = t.scrollTop;
  }, []);

  useLayoutEffect(syncScroll, [value, syncScroll]);

  /** Replace the current selection, keeping undo history where possible. */
  const replaceSelection = (text: string, selectStart: number, selectEnd: number) => {
    const t = textRef.current!;
    t.focus();
    // execCommand keeps the native undo stack intact; the fallback does not,
    // but it is only reached in browsers that have removed execCommand.
    const ok = document.execCommand?.("insertText", false, text);
    if (!ok) {
      const next = t.value.slice(0, t.selectionStart) + text + t.value.slice(t.selectionEnd);
      onChange(next);
    }
    requestAnimationFrame(() => t.setSelectionRange(selectStart, selectEnd));
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const t = e.currentTarget;
    const { selectionStart: start, selectionEnd: end, value: text } = t;

    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      onRun?.();
      return;
    }
    if (e.key === "Escape") {
      setTabTrapped(false);
      return;
    }
    if (e.key === "Tab" && tabTrapped) {
      e.preventDefault();
      const lineStart = text.lastIndexOf("\n", start - 1) + 1;
      const multiLine = text.slice(start, end).includes("\n");

      if (!e.shiftKey && !multiLine) {
        replaceSelection(INDENT, start + INDENT.length, start + INDENT.length);
        return;
      }
      // Indent or dedent every line the selection touches.
      const blockEnd = end > start && text[end - 1] === "\n" ? end - 1 : end;
      const block = text.slice(lineStart, blockEnd);
      const lines = block.split("\n");
      const changed = lines.map((line) =>
        e.shiftKey ? line.replace(/^( {1,4}|\t)/, "") : INDENT + line,
      );
      const replaced = changed.join("\n");
      t.setSelectionRange(lineStart, blockEnd);
      replaceSelection(replaced, lineStart, lineStart + replaced.length);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.altKey) {
      // Keep the indentation of the current line, and add a level after a
      // colon -- the one piece of structure Python makes you type yourself.
      const lineStart = text.lastIndexOf("\n", start - 1) + 1;
      const line = text.slice(lineStart, start);
      const indent = line.match(/^[ \t]*/)?.[0] ?? "";
      const extra = /:\s*(#.*)?$/.test(line) ? INDENT : "";
      e.preventDefault();
      const insert = "\n" + indent + extra;
      replaceSelection(insert, start + insert.length, start + insert.length);
      return;
    }
    if (e.key === "Backspace" && start === end && start > 0) {
      // Delete a whole indent level when the caret sits in leading spaces.
      const lineStart = text.lastIndexOf("\n", start - 1) + 1;
      const before = text.slice(lineStart, start);
      if (before.length > 0 && /^ +$/.test(before)) {
        const remove = ((before.length - 1) % INDENT.length) + 1;
        e.preventDefault();
        t.setSelectionRange(start - remove, start);
        replaceSelection("", start - remove, start - remove);
      }
    }
  };

  return (
    <div className="code-editor">
      <div className="ce-gutter" ref={gutterRef} aria-hidden="true">
        {Array.from({ length: lineCount }, (_, i) => (
          <div key={i}>{i + 1}</div>
        ))}
      </div>
      <div className="ce-body">
        <pre
          ref={preRef}
          className="ce-highlight"
          aria-hidden="true"
          dangerouslySetInnerHTML={{ __html: html }}
        />
        <textarea
          ref={textRef}
          className="ce-input"
          value={value}
          spellCheck={false}
          autoCapitalize="off"
          autoCorrect="off"
          autoComplete="off"
          wrap="off"
          aria-label={label}
          aria-describedby="ce-help"
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
          onScroll={syncScroll}
          onFocus={() => setTabTrapped(true)}
          placeholder="# Write Python here, then press Run (Ctrl+Enter)"
        />
      </div>
      <p id="ce-help" className="visually-hidden">
        Tab indents and Shift+Tab dedents. Press Escape, then Tab, to move focus
        out of the editor. Control+Enter runs the program.
      </p>
    </div>
  );
}
