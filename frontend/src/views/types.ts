import type { Annotation, ExecutionState, HeapObject, ViewDescriptor } from "../api/types";

/**
 * The complete view contract.
 *
 * Notice what is absent: the algorithm id, the plugin, the source, the event
 * stream. A view cannot depend on them because it is not given them. That is
 * the mechanical form of "no algorithm-specific visualization logic in the core
 * renderer" (docs/08 §N.4).
 */
export interface ViewProps {
  object: HeapObject;
  heap: Record<string, HeapObject>;
  /** Annotations targeting this object. */
  annotations: Annotation[];
  /**
   * Every live annotation, whatever it targets.
   *
   * Needed because an annotation's target is the container it was *emitted
   * against*, which is not always the thing it describes. A graph traversal
   * marks nodes by adding them to a `visited` set, so the visit annotations
   * target that set -- yet what they describe is a node of the graph. A view
   * that only saw its own annotations could never draw the traversal.
   */
  allAnnotations: Annotation[];
  state: ExecutionState;
  descriptor: ViewDescriptor;
  onSelect?: (ref: string, path?: (string | number)[]) => void;
}

/** Annotations that describe a node identity rather than a container slot. */
export const NODE_ANNOTATION_KINDS = new Set([
  "visit", "discover", "relax", "mark", "unmark",
]);

export function nodeAnnotations(all: Annotation[]): Annotation[] {
  return all.filter((a) => NODE_ANNOTATION_KINDS.has(a.kind));
}

export function annotationsFor(all: Annotation[], ref: string): Annotation[] {
  return all.filter((a) => a.target_ref === ref);
}

export const MARK_COLORS: Record<string, string> = {
  visit: "var(--accent-visited)",
  discover: "var(--accent-frontier)",
  compare: "var(--accent-compare)",
  swap: "var(--accent-swap)",
  relax: "var(--accent-relax)",
  highlight: "var(--accent-compare)",
  mark: "var(--accent-mark)",
  pivot: "var(--accent-mark)",
};
