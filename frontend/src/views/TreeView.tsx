import { useMemo } from "react";
import { treeLayout, type PlacedNode, type TreeNodeShape } from "../lib/layout";
import { preview } from "../lib/format";
import type { HeapObject } from "../api/types";
import { MARK_COLORS, nodeAnnotations, type ViewProps } from "./types";

/** Layered tree over objects linked by the detected child fields. */
export function TreeView({ object, heap, descriptor, allAnnotations, state }: ViewProps) {
  const childFields = (descriptor.props.children as string[]) ?? ["left", "right"];

  const roots = useMemo<TreeNodeShape[]>(() => {
    const seen = new Set<string>();
    const build = (record: HeapObject | undefined): TreeNodeShape | null => {
      if (!record || seen.has(record.ref)) return null;
      seen.add(record.ref);
      const fields = record.fields ?? {};
      const valueKey =
        Object.keys(fields).find((k) => !childFields.includes(k)) ?? "";
      const children: TreeNodeShape[] = [];
      for (const field of childFields) {
        const value = fields[field];
        if (value && (value as any).k === "ref") {
          const child = build(heap[(value as any).r]);
          if (child) children.push(child);
        }
      }
      return {
        id: record.ref,
        label: preview(fields[valueKey], 8),
        children,
      };
    };
    const root = build(object);
    return root ? [root] : [];
  }, [object, heap, childFields]);

  const { nodes, width, height } = useMemo(() => treeLayout(roots), [roots]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const marks = new Map<string, string>();
  for (const a of nodeAnnotations(allAnnotations)) {
    const color = MARK_COLORS[a.kind];
    if (color && a.target_ref) marks.set(a.target_ref, color);
  }

  /* Which nodes are variables currently pointing at? That is where the
     algorithm *is*, and it needs no annotation to work out -- a recursive
     `insert(node, value)` puts `node` on the frame, and the frame is state. */
  const cursors = useMemo(() => {
    const frame = state.frames[state.frames.length - 1];
    const out = new Map<string, string[]>();
    if (!frame) return out;
    for (const [name, value] of Object.entries(frame.locals)) {
      if (!value || (value as any).k !== "ref") continue;
      const ref = (value as any).r as string;
      if (!byId.has(ref)) continue;
      (out.get(ref) ?? out.set(ref, []).get(ref)!).push(name);
    }
    return out;
  }, [state.frames, byId]);

  /* The route from the root down to the deepest cursor: the search path. */
  const pathRefs = useMemo(() => {
    const deepest = [...cursors.keys()]
      .map((ref) => byId.get(ref))
      .filter((n): n is NonNullable<typeof n> => Boolean(n))
      .sort((a, b) => b.depth - a.depth)[0];
    const path = new Set<string>();
    let node: PlacedNode | undefined = deepest;
    while (node) {
      path.add(node.id);
      node = node.parent ? byId.get(node.parent) : undefined;
    }
    return path;
  }, [cursors, byId]);

  if (!nodes.length) return <div className="view empty">no nodes</div>;

  return (
    <div className="view tree-view">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label={
          `Tree of ${nodes.length} nodes` +
          (pathRefs.size > 1 ? `, with a path of ${pathRefs.size} nodes highlighted` : "") +
          "."
        }
      >
        {nodes.map((node) => {
          const parent = node.parent ? byId.get(node.parent) : undefined;
          if (!parent) return null;
          const onPath = pathRefs.has(node.id) && pathRefs.has(parent.id);
          return (
            <line
              key={`e-${node.id}`}
              x1={parent.x} y1={parent.y} x2={node.x} y2={node.y}
              className={`tv-edge${onPath ? " on-path" : ""}`}
            />
          );
        })}
        {nodes.map((node) => {
          const names = cursors.get(node.id);
          const isCursor = Boolean(names);
          const onPath = pathRefs.has(node.id);
          const marked = marks.get(node.id);
          return (
            <g key={node.id} transform={`translate(${node.x},${node.y})`}
               className={`tv-node${isCursor ? " cursor" : onPath ? " on-path" : ""}`}>
              {isCursor && <circle r={21} className="tv-halo" />}
              <circle r={15} className="tv-circle"
                      style={marked ? { fill: marked } : undefined} />
              <text className="node-label" textAnchor="middle" dy="4">{node.label}</text>
              {names && (
                <text className="tv-cursor-label" textAnchor="middle" dy="-22">
                  {names.join(", ")}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {cursors.size > 0 && (
        <div className="gv-legend">
          <span><i className="current" /> where the algorithm is</span>
          <span><i className="path" /> path from the root</span>
        </div>
      )}
    </div>
  );
}

/**
 * The recursion tree, built from FUNCTION_ENTERED/EXITED events.
 *
 * This is the generic call tree. For `fib(5)` it happens to look like the
 * familiar Fibonacci diagram; for merge sort it looks like a divide-and-conquer
 * split. Neither shape is special-cased.
 */
export function CallTreeView({ state }: { state: ViewProps["state"] }) {
  const { nodes, width, height, activeIds } = useMemo(() => {
    const records = state.call_tree;
    const children = new Map<number, TreeNodeShape[]>();
    const shapes = new Map<number, TreeNodeShape>();
    for (const record of records) {
      const args = Object.entries(record.args ?? {})
        .map(([, v]) => preview(v as any, 6))
        .join(",");
      const shape: TreeNodeShape = {
        id: String(record.frame_id),
        label: `${record.name}(${args})`,
        children: [],
        meta: { returned: record.return_value, exited: record.exit_step >= 0 },
      };
      shapes.set(record.frame_id, shape);
      (children.get(record.parent) ?? children.set(record.parent, []).get(record.parent)!)
        .push(shape);
    }
    for (const record of records) {
      const kids = children.get(record.frame_id) ?? [];
      shapes.get(record.frame_id)!.children = kids;
    }
    const roots = (children.get(0) ?? []).concat(children.get(-1) ?? []);
    const layout = treeLayout(roots, 108, 54);
    const active = new Set(state.frames.map((f) => String(f.frame_id)));
    return { ...layout, activeIds: active };
  }, [state.call_tree, state.frames]);

  if (!nodes.length) return <div className="view empty">no calls yet</div>;
  const byId = new Map(nodes.map((n) => [n.id, n]));

  return (
    <div className="view calltree-view">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        height={Math.min(height, 320)}
        role="img"
        aria-label={`Call tree with ${nodes.length} calls, ${activeIds.size} still on the stack.`}
      >
        {nodes.map((node) =>
          node.parent && byId.has(node.parent) ? (
            <line
              key={`e-${node.id}`}
              x1={byId.get(node.parent)!.x} y1={byId.get(node.parent)!.y}
              x2={node.x} y2={node.y}
              stroke="var(--edge)" strokeWidth={1}
            />
          ) : null,
        )}
        {nodes.map((node) => {
          const active = activeIds.has(node.id);
          const returned = (node.meta as any)?.returned;
          return (
            <g key={node.id} transform={`translate(${node.x},${node.y})`}>
              <rect
                x={-46} y={-13} width={92} height={26} rx={5}
                fill={active ? "var(--accent-current)" : "var(--node)"}
                stroke="var(--edge)"
              />
              <text className="node-label" textAnchor="middle" dy="-1">{node.label}</text>
              {returned != null && (
                <text className="node-badge" textAnchor="middle" dy="10">
                  → {preview(returned, 8)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
