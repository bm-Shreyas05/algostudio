import { useMemo } from "react";
import { forceLayout, type GraphEdge, type GraphNode } from "../lib/layout";
import { scalarOf } from "../lib/format";
import { nodeAnnotations, type ViewProps } from "./types";

const WIDTH = 520;
const HEIGHT = 360;

/** A node currently held by a variable, e.g. `u` in Dijkstra's outer loop. */
interface Cursor { id: string; names: string[] }

/**
 * Nodes, edges, and the route the algorithm has taken through them.
 *
 * Everything drawn comes from three generic sources, none of which name an
 * algorithm:
 *
 *   * the detector's derived node/edge lists;
 *   * `visit` annotations, which carry a step, so their order *is* the
 *     traversal order;
 *   * bindings in the active frame whose value equals a node id -- that is how
 *     `u`, `v` and `node` get drawn onto the graph as labelled cursors.
 */
export function GraphView({ descriptor, allAnnotations, state }: ViewProps) {
  const nodes = (descriptor.props.nodes ?? []) as GraphNode[];
  const edges = (descriptor.props.edges ?? []) as GraphEdge[];
  const weighted = Boolean(descriptor.props.weighted);

  const positions = useMemo(
    () => forceLayout(nodes, edges, WIDTH, HEIGHT),
    [nodes, edges],
  );

  /* ---- traversal order, from the visit annotations --------------------- */
  const marks = useMemo(() => nodeAnnotations(allAnnotations), [allAnnotations]);

  const { order, current, discovered } = useMemo(() => {
    const visits = marks
      .filter((a) => a.kind === "visit")
      .map((a) => ({ id: nodeId(a.value?.node), step: a.step }))
      .filter((v) => v.id !== null)
      .sort((a, b) => a.step - b.step);

    const seen = new Map<string, number>();
    visits.forEach((v) => {
      if (!seen.has(v.id!)) seen.set(v.id!, seen.size + 1);
    });
    const found = new Set(
      marks
        .filter((a) => a.kind === "discover")
        .map((a) => nodeId(a.value?.node))
        .filter((id): id is string => id !== null),
    );
    return {
      order: seen,
      current: visits.length ? visits[visits.length - 1].id : null,
      discovered: found,
    };
  }, [marks]);

  /* ---- variables pointing at nodes ------------------------------------- */
  const cursors = useMemo<Cursor[]>(() => {
    const frame = state.frames[state.frames.length - 1];
    if (!frame) return [];
    const ids = new Set(nodes.map((n) => String(n.id)));
    const byNode = new Map<string, string[]>();
    for (const [name, value] of Object.entries(frame.locals)) {
      const scalar = scalarOf(value);
      if (scalar === null || scalar === undefined) continue;
      const key = String(scalar);
      if (!ids.has(key)) continue;
      (byNode.get(key) ?? byNode.set(key, []).get(key)!).push(name);
    }
    return [...byNode.entries()].map(([id, names]) => ({ id, names }));
  }, [state.frames, nodes]);
  const cursorFor = useMemo(
    () => new Map(cursors.map((c) => [c.id, c.names.join(", ")])),
    [cursors],
  );

  /* ---- the edge being worked on right now ------------------------------ */
  const activeEdges = useMemo(() => {
    const set = new Set<string>();
    for (const a of marks) {
      if (a.kind !== "relax" && a.kind !== "discover") continue;
      const from = nodeId(a.value?.u) ?? nodeId(a.value?.via);
      const to = nodeId(a.value?.v) ?? nodeId(a.value?.node);
      if (from && to) {
        set.add(`${from}->${to}`);
        set.add(`${to}->${from}`);
      }
    }
    return set;
  }, [marks]);

  /* ---- the route, as a dashed trail through the visits ------------------ */
  const trail = useMemo(() => {
    const sequence = [...order.entries()].sort((a, b) => a[1] - b[1]).map(([id]) => id);
    const segments: { from: string; to: string; adjacent: boolean }[] = [];
    const adjacency = new Set(edges.flatMap((e) => [`${e.source}->${e.target}`, `${e.target}->${e.source}`]));
    for (let i = 0; i < sequence.length - 1; i++) {
      segments.push({
        from: sequence[i],
        to: sequence[i + 1],
        adjacent: adjacency.has(`${sequence[i]}->${sequence[i + 1]}`),
      });
    }
    return segments;
  }, [order, edges]);

  if (!nodes.length) return <div className="view empty">No nodes yet.</div>;

  return (
    <div className="view graph-view">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} width="100%" preserveAspectRatio="xMidYMid meet">
        <defs>
          <marker id="gv-arrow" viewBox="0 0 10 10" refX="20" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--edge)" />
          </marker>
          <marker id="gv-arrow-hot" viewBox="0 0 10 10" refX="20" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent-relax)" />
          </marker>
          <marker id="gv-arrow-trail" viewBox="0 0 10 10" refX="19" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--accent-visited)" />
          </marker>
        </defs>

        {/* graph edges */}
        {edges.map((edge, i) => {
          const a = positions[edge.source];
          const b = positions[edge.target];
          if (!a || !b) return null;
          const hot = activeEdges.has(`${edge.source}->${edge.target}`);
          return (
            <g key={`e${i}`}>
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                className={`gv-edge${hot ? " hot" : ""}`}
                markerEnd={hot ? "url(#gv-arrow-hot)" : "url(#gv-arrow)"}
              />
              {weighted && edge.weight !== undefined && (
                <text
                  x={(a.x + b.x) / 2} y={(a.y + b.y) / 2 - 5}
                  className="edge-label" textAnchor="middle"
                >
                  {edge.weight}
                </text>
              )}
            </g>
          );
        })}

        {/* the traversal route: dashed so it is never mistaken for a real edge */}
        {trail.map((seg, i) => {
          const a = positions[seg.from];
          const b = positions[seg.to];
          if (!a || !b) return null;
          return (
            <line
              key={`t${i}`}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              className={`gv-trail${seg.adjacent ? "" : " jump"}`}
              markerEnd="url(#gv-arrow-trail)"
            />
          );
        })}

        {/* nodes */}
        {nodes.map((node) => {
          const p = positions[node.id];
          if (!p) return null;
          const id = String(node.id);
          const rank = order.get(id);
          const isCurrent = id === current;
          const cursor = cursorFor.get(id);
          const state_ =
            isCurrent ? "current"
            : rank !== undefined ? "visited"
            : discovered.has(id) ? "frontier"
            : "unvisited";
          return (
            <g key={id} transform={`translate(${p.x},${p.y})`} className={`gv-node ${state_}`}>
              {isCurrent && <circle r={22} className="gv-halo" />}
              <circle r={16} className="gv-circle" />
              <text className="node-label" textAnchor="middle" dy="4">{id}</text>
              {rank !== undefined && (
                <g transform="translate(14,-14)">
                  <circle r={8} className="gv-rank-bg" />
                  <text className="gv-rank" textAnchor="middle" dy="3">{rank}</text>
                </g>
              )}
              {cursor && (
                <text className="gv-cursor" textAnchor="middle" dy="-24">{cursor}</text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="gv-legend">
        <span><i className="current" /> current</span>
        <span><i className="visited" /> visited <b>①②③</b> = order</span>
        <span><i className="frontier" /> discovered</span>
        <span><i className="trail" /> route taken</span>
        {cursors.length > 0 && (
          <span className="muted">
            labels above nodes are variables pointing at them
          </span>
        )}
      </div>
    </div>
  );
}

function nodeId(value: unknown): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "object") {
    const scalar = (value as any).v;
    return scalar === undefined || scalar === null ? null : String(scalar);
  }
  return String(value);
}
