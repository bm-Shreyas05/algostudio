/** Deterministic layout helpers. Seeded so a graph does not jump between steps. */

export interface Pt { x: number; y: number }

export interface GraphNode { id: string }
export interface GraphEdge { source: string; target: string; weight?: number }

function seeded(seed: number): () => number {
  let s = seed >>> 0 || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s / 4294967296;
  };
}

function hash(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i++) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/**
 * Circular seed plus a fixed number of force iterations.
 *
 * Seeded by the node-id set, so the same graph lays out identically on every
 * step and across reloads -- a layout that drifts while you scrub the timeline
 * makes it impossible to track a node.
 */
export function forceLayout(
  nodes: GraphNode[], edges: GraphEdge[], width: number, height: number,
): Record<string, Pt> {
  const n = nodes.length;
  if (n === 0) return {};
  const rng = seeded(hash(nodes.map((v) => v.id).join(",")));
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.36;
  const pos: Record<string, Pt> = {};
  nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / n + rng() * 0.2;
    pos[node.id] = { x: cx + radius * Math.cos(angle), y: cy + radius * Math.sin(angle) };
  });
  if (n === 1) return pos;

  const ideal = Math.max(48, Math.min(width, height) / (Math.sqrt(n) + 1));
  const adjacency = new Map<string, Set<string>>();
  for (const node of nodes) adjacency.set(node.id, new Set());
  for (const e of edges) {
    adjacency.get(e.source)?.add(e.target);
    adjacency.get(e.target)?.add(e.source);
  }

  for (let iter = 0; iter < 220; iter++) {
    const cooling = 1 - iter / 220;
    const force: Record<string, Pt> = {};
    for (const node of nodes) force[node.id] = { x: 0, y: 0 };

    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = nodes[i].id;
        const b = nodes[j].id;
        let dx = pos[a].x - pos[b].x;
        let dy = pos[a].y - pos[b].y;
        let dist = Math.hypot(dx, dy) || 0.01;
        if (dist < 1) { dx = rng() - 0.5; dy = rng() - 0.5; dist = 1; }
        const repulse = (ideal * ideal) / dist;
        force[a].x += (dx / dist) * repulse;
        force[a].y += (dy / dist) * repulse;
        force[b].x -= (dx / dist) * repulse;
        force[b].y -= (dy / dist) * repulse;
      }
    }
    for (const e of edges) {
      const a = pos[e.source];
      const b = pos[e.target];
      if (!a || !b) continue;
      const dx = a.x - b.x;
      const dy = a.y - b.y;
      const dist = Math.hypot(dx, dy) || 0.01;
      const attract = (dist * dist) / ideal;
      force[e.source].x -= (dx / dist) * attract;
      force[e.source].y -= (dy / dist) * attract;
      force[e.target].x += (dx / dist) * attract;
      force[e.target].y += (dy / dist) * attract;
    }
    for (const node of nodes) {
      const f = force[node.id];
      const magnitude = Math.hypot(f.x, f.y) || 0.01;
      const limit = Math.min(magnitude, ideal * 0.6 * cooling);
      const p = pos[node.id];
      p.x = Math.max(24, Math.min(width - 24, p.x + (f.x / magnitude) * limit));
      p.y = Math.max(24, Math.min(height - 24, p.y + (f.y / magnitude) * limit));
    }
  }
  return pos;
}

export interface TreeNodeShape {
  id: string;
  label: string;
  children: TreeNodeShape[];
  meta?: Record<string, unknown>;
}

export interface PlacedNode extends Pt {
  id: string;
  label: string;
  depth: number;
  meta?: Record<string, unknown>;
  parent?: string;
}

/** Tidy layered layout: leaves get consecutive slots, parents centre over them. */
export function treeLayout(
  roots: TreeNodeShape[], gapX = 74, gapY = 62,
): { nodes: PlacedNode[]; width: number; height: number } {
  const placed: PlacedNode[] = [];
  let cursor = 0;
  let maxDepth = 0;

  const walk = (node: TreeNodeShape, depth: number, parent?: string): number => {
    maxDepth = Math.max(maxDepth, depth);
    if (!node.children.length) {
      const x = cursor++;
      placed.push({ id: node.id, label: node.label, x, y: depth, depth, meta: node.meta, parent });
      return x;
    }
    const kids = node.children.map((child) => walk(child, depth + 1, node.id));
    const x = (kids[0] + kids[kids.length - 1]) / 2;
    placed.push({ id: node.id, label: node.label, x, y: depth, depth, meta: node.meta, parent });
    return x;
  };

  for (const root of roots) walk(root, 0);
  for (const node of placed) {
    node.x = node.x * gapX + gapX / 2;
    node.y = node.y * gapY + gapY / 2;
  }
  return {
    nodes: placed,
    width: Math.max(cursor * gapX + gapX, 240),
    height: (maxDepth + 1) * gapY + gapY / 2,
  };
}
