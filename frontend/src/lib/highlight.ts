/**
 * Python syntax highlighting, without a dependency.
 *
 * This app ships React and nothing else on purpose, and a full editor library
 * is 150 KB or more for a feature that needs a few hundred lines. The job is
 * modest: colour the tokens a student reads -- keywords, strings, numbers,
 * comments, the names being defined -- well enough that structure is visible
 * at a glance. It is not a parser and does not try to be: a token it cannot
 * classify is simply left plain, which is always a safe failure.
 *
 * One tokenizer serves both the editor and the read-only trace view, so code
 * looks the same while you write it and while you watch it run.
 */

const KEYWORDS = new Set([
  "and", "as", "assert", "async", "await", "break", "case", "class", "continue",
  "def", "del", "elif", "else", "except", "finally", "for", "from", "global",
  "if", "import", "in", "is", "lambda", "match", "nonlocal", "not", "or",
  "pass", "raise", "return", "try", "while", "with", "yield",
]);

const CONSTANTS = new Set(["None", "True", "False"]);

const BUILTINS = new Set([
  "abs", "all", "any", "bool", "dict", "divmod", "enumerate", "filter", "float",
  "frozenset", "hash", "id", "input", "int", "isinstance", "iter", "len", "list",
  "map", "max", "min", "next", "object", "ord", "chr", "pow", "print", "range",
  "reversed", "round", "set", "sorted", "str", "sum", "super", "tuple", "type",
  "zip", "algo",
]);

/**
 * One alternation, tried left to right at each position. Order matters:
 * strings and comments first, so that a `#` inside a string, or a quote inside a
 * comment, is never mistaken for the start of the other.
 */
const TOKEN = new RegExp(
  [
    String.raw`(?<comment>#[^\n]*)`,
    // triple-quoted strings (possibly unterminated -- still colour them)
    String.raw`(?<tstring>(?:[rRbBuUfF]{0,2})(?:"""[\s\S]*?(?:"""|$)|'''[\s\S]*?(?:'''|$)))`,
    String.raw`(?<string>(?:[rRbBuUfF]{0,2})(?:"(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?))`,
    String.raw`(?<decorator>@[A-Za-z_][\w.]*)`,
    String.raw`(?<number>\b(?:0[xX][\da-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+|\d[\d_]*\.?[\d_]*(?:[eE][+-]?\d+)?j?)\b)`,
    String.raw`(?<name>[A-Za-z_]\w*)`,
    String.raw`(?<op>[-+*/%=<>!&|^~]+|[()[\]{}:,.;])`,
  ].join("|"),
  "g",
);

export type TokenKind =
  | "comment" | "string" | "decorator" | "number" | "keyword" | "constant"
  | "builtin" | "defname" | "self" | "op" | "plain";

export interface Token {
  kind: TokenKind;
  text: string;
}

export function tokenize(source: string): Token[] {
  const out: Token[] = [];
  let last = 0;
  // Is the next identifier the name being defined by `def` or `class`?
  let expectDefName = false;

  TOKEN.lastIndex = 0;
  for (let m = TOKEN.exec(source); m; m = TOKEN.exec(source)) {
    if (m[0] === "") {                      // never loop on an empty match
      TOKEN.lastIndex++;
      continue;
    }
    if (m.index > last) out.push({ kind: "plain", text: source.slice(last, m.index) });
    const g = m.groups!;
    const text = m[0];

    if (g.comment !== undefined) out.push({ kind: "comment", text });
    else if (g.tstring !== undefined || g.string !== undefined) out.push({ kind: "string", text });
    else if (g.decorator !== undefined) out.push({ kind: "decorator", text });
    else if (g.number !== undefined) out.push({ kind: "number", text });
    else if (g.name !== undefined) {
      let kind: TokenKind = "plain";
      if (expectDefName) kind = "defname";
      else if (KEYWORDS.has(text)) kind = "keyword";
      else if (CONSTANTS.has(text)) kind = "constant";
      else if (text === "self" || text === "cls") kind = "self";
      else if (BUILTINS.has(text)) kind = "builtin";
      out.push({ kind, text });
      expectDefName = text === "def" || text === "class";
      last = TOKEN.lastIndex;
      continue;
    } else out.push({ kind: "op", text });

    expectDefName = false;
    last = TOKEN.lastIndex;
  }
  if (last < source.length) out.push({ kind: "plain", text: source.slice(last) });
  return out;
}

const ESCAPE: Record<string, string> = { "&": "&amp;", "<": "&lt;", ">": "&gt;" };
const escape = (s: string) => s.replace(/[&<>]/g, (c) => ESCAPE[c]);

/**
 * Highlighted HTML for a block of source. Only ever built from our own token
 * kinds and HTML-escaped text, so it is safe to set as innerHTML.
 */
export function highlightHtml(source: string): string {
  return tokenize(source)
    .map((t) => (t.kind === "plain" ? escape(t.text) : `<span class="tk-${t.kind}">${escape(t.text)}</span>`))
    .join("");
}

/**
 * The same highlighting, split into one HTML string per source line.
 *
 * The trace view renders a row per line (it needs a gutter, hit counts and a
 * current-line marker on each), so it cannot take one block of HTML. But it
 * must still tokenize the *whole* source: a triple-quoted string spanning three
 * lines is a string on all three, which per-line tokenizing would get wrong.
 * So tokenize once, then cut every token at its newlines.
 */
export function highlightLines(source: string): string[] {
  const lines: string[] = [""];
  for (const token of tokenize(source)) {
    const pieces = token.text.split("\n");
    pieces.forEach((piece, i) => {
      if (i > 0) lines.push("");
      if (!piece) return;
      lines[lines.length - 1] += token.kind === "plain"
        ? escape(piece)
        : `<span class="tk-${token.kind}">${escape(piece)}</span>`;
    });
  }
  return lines;
}
