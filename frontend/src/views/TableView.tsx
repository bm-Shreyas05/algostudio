import { preview } from "../lib/format";
import { MARK_COLORS, type ViewProps } from "./types";

/** Key/value rows. Serves dicts, and object field tables. */
export function TableView({ object, annotations }: ViewProps) {
  const entries = object.entries ?? [];
  const fields = object.fields ? Object.entries(object.fields) : [];
  const hot = new Set(
    annotations
      .filter((a) => MARK_COLORS[a.kind])
      .map((a) => String(a.value?.v ?? a.value?.index ?? a.index ?? "")),
  );

  const rows: [string, any][] = object.fields
    ? fields
    : entries.map(([k, v]) => [preview(k, 24), v]);

  if (!rows.length) return <div className="view empty">empty</div>;

  return (
    <div className="view table-view">
      <table>
        <tbody>
          {rows.map(([key, value], i) => (
            <tr key={i} className={hot.has(String(key)) ? "hot" : undefined}>
              <td className="k">{key}</td>
              <td className="v">{preview(value, 40)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {object.trunc && <div className="truncated-note">…{object.n} entries total</div>}
    </div>
  );
}

/** Membership chips, insertion-ordered. */
export function SetView({ object }: ViewProps) {
  const items = object.items ?? [];
  if (!items.length) return <div className="view empty">empty set</div>;
  return (
    <div className="view set-view">
      {items.map((item, i) => (
        <span key={i} className="chip">{preview(item, 16)}</span>
      ))}
      {object.trunc && <span className="chip muted">…{object.n}</span>}
    </div>
  );
}

/** Field table for a user-defined object, with ref arrows. */
export function ObjectView({ object, heap }: ViewProps) {
  const fields = Object.entries(object.fields ?? {});
  return (
    <div className="view object-view">
      <div className="object-class">{object.cls ?? object.t}</div>
      <table>
        <tbody>
          {fields.map(([name, value]) => {
            const ref = (value as any)?.k === "ref" ? (value as any).r : null;
            const target = ref ? heap[ref] : null;
            return (
              <tr key={name}>
                <td className="k">{name}</td>
                <td className="v">
                  {preview(value, 30)}
                  {target && <span className="ref-arrow">→ {target.cls ?? target.t}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Numeric grid with row/column headers. */
export function MatrixView({ object, heap }: ViewProps) {
  const rows = (object.items ?? []).map((item) =>
    (item as any)?.k === "ref" ? heap[(item as any).r] : null,
  );
  return (
    <div className="view matrix-view">
      <table>
        <tbody>
          {rows.map((row, r) => (
            <tr key={r}>
              <td className="hdr">{r}</td>
              {(row?.items ?? []).map((cell, c) => (
                <td key={c} className="cell">{preview(cell, 8)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Fallback for anything with no better representation. */
export function ValueView({ object }: ViewProps) {
  return (
    <div className="view value-view">
      <pre>{JSON.stringify(object, null, 1).slice(0, 1200)}</pre>
    </div>
  );
}
