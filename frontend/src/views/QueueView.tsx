import { preview, scalarOf } from "../lib/format";
import type { ViewProps } from "./types";

/** Horizontal, with the front and back ends labelled. */
export function QueueView({ object }: ViewProps) {
  const items = object.items ?? [];
  return (
    <div className="view queue-view">
      <span className="end-label">front</span>
      <div className="queue-cells">
        {items.length === 0 && <span className="muted">empty</span>}
        {items.map((item, i) => (
          <span key={i} className="queue-cell">{preview(item, 12)}</span>
        ))}
      </div>
      <span className="end-label">back</span>
    </div>
  );
}

/** Vertical, top of stack at the top. */
export function StackView({ object }: ViewProps) {
  const items = [...(object.items ?? [])].reverse();
  return (
    <div className="view stack-view">
      {items.length === 0 && <span className="muted">empty</span>}
      {items.map((item, i) => (
        <div key={i} className={`stack-cell${i === 0 ? " top" : ""}`}>
          {i === 0 && <span className="end-label">top</span>}
          {preview(item, 16)}
        </div>
      ))}
    </div>
  );
}

/**
 * A binary heap shown twice -- as a tree and as its backing array -- with the
 * two representations index-linked, which is the thing students find hardest to
 * hold in their heads.
 */
export function HeapView({ object }: ViewProps) {
  const items = object.items ?? [];
  const values = items.map((v) => scalarOf(v));
  const levels: number[][] = [];
  for (let i = 0; i < values.length; i++) {
    const depth = Math.floor(Math.log2(i + 1));
    (levels[depth] ??= []).push(i);
  }
  return (
    <div className="view heap-view">
      <div className="heap-tree">
        {levels.map((level, depth) => (
          <div key={depth} className="heap-level">
            {level.map((index) => (
              <span key={index} className="heap-node" title={`index ${index}`}>
                {preview(items[index], 8)}
                <small>{index}</small>
              </span>
            ))}
          </div>
        ))}
      </div>
      <div className="heap-array">
        {items.map((item, i) => (
          <span key={i} className="heap-cell">
            {preview(item, 8)}
            <small>{i}</small>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Node boxes chained by the detected `next` field; cycle-safe. */
export function LinkedListView({ object, heap, descriptor }: ViewProps) {
  const nextField = (descriptor.props.next as string) ?? "next";
  const chain: { ref: string; label: string }[] = [];
  const seen = new Set<string>();
  let current: any = object;
  while (current && !seen.has(current.ref)) {
    seen.add(current.ref);
    const fields = current.fields ?? {};
    const valueKey = Object.keys(fields).find((k) => k !== nextField) ?? "";
    chain.push({ ref: current.ref, label: preview(fields[valueKey], 10) });
    const next = fields[nextField];
    current = next && (next as any).k === "ref" ? heap[(next as any).r] : null;
    if (chain.length > 60) break;
  }
  return (
    <div className="view linked-view">
      {chain.map((node, i) => (
        <span key={node.ref} className="linked-node">
          {node.label}
          {i < chain.length - 1 && <span className="linked-arrow">→</span>}
        </span>
      ))}
      {current && <span className="linked-arrow muted">↺ cycle</span>}
    </div>
  );
}
