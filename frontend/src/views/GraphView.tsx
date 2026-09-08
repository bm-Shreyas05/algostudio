import { useMemo } from "react";
import { forceLayout, type GraphEdge, type GraphNode } from "../lib/layout";
import { scalarOf } from "../lib/format";
import { MARK_COLORS, type ViewProps } from "./types";

const WIDTH = 460;
const HEIGHT = 300;

/**
 * Nodes and edges come from the detector's derived props, and node states come
 * from annotations. No traversal logic lives here -- this component cannot tell
 * BFS from Dijkstra from something a student invented.
 */
export function GraphView({ descriptor, annotations }: ViewProps) {
  const nodes = (descriptor.props.nodes ?? []) as GraphNode[];
  const edges = (descriptor.props.edges ?? []) as GraphEdge[];
  const weighted = Boolean(descriptor.props.weighted);

  const positions = useMemo(
    () => forceLayout(nodes, edges, WIDTH, HEIGHT),
    [nodes, edges],
  );

  const marks = new Map<string, string>();
  const labels = new Map<string, string>();
  for (const a of annotations) {
    const color = MARK_COLORS[a.kind];
    const node = scalarOf(a.value?.node) ?? a.value?.node ?? a.value?.target;
    const id = typeof node === "object" ? (node as any)?.v : node;
    if (color && id !== undefined && id !== null) {
      marks.set(String(id), color);
      if (a.kind !== "visit") labels.set(String(id), a.kind);
    }
  }
  const activeEdge = annotations.find((a) => a.kind === "relax");
  const activeKey = activeEdge
    ? `${scalarOf(activeEdge.value?.u) ?? activeEdge.value?.u}->${scalarOf(activeEdge.value?.v) ?? activeEdge.value?.v}`
    : "";

  if (!nodes.length) return <div className="view empty">No nodes yet.</div>;

  return (
    <div className="view graph-view">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" height={HEIGHT}>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="18" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--edge)" />
          </marker>
        </defs>
        {edges.map((edge, i) => {
          const a = positions[edge.source];
          const b = positions[edge.target];
          if (!a || !b) return null;
          const key = `${edge.source}->${edge.target}`;
          const hot = key === activeKey;
          return (
            <g key={i}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke={hot ? "var(--accent-relax)" : "var(--edge)"}
                strokeWidth={hot ? 2.5 : 1.2}
                markerEnd="url(#arrow)"
              />
              {weighted && edge.weight !== undefined && (
                <text
                  x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 4}
                  className="edge-label" textAnchor="middle"
                >
                  {edge.weight}
                </text>
              )}
            </g>
          );
        })}
        {nodes.map((node) => {
          const p = positions[node.id];
          if (!p) return null;
          const fill = marks.get(node.id);
          return (
            <g key={node.id} transform={`translate(${p.x},${p.y})`}>
              <circle
                r={16}
                fill={fill ?? "var(--node)"}
                stroke={fill ? "var(--fg)" : "var(--edge)"}
                strokeWidth={fill ? 2 : 1}
              />
              <text className="node-label" textAnchor="middle" dy="4">
                {node.id}
              </text>
              {labels.has(node.id) && (
                <text className="node-badge" textAnchor="middle" dy="-22">
                  {labels.get(node.id)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
