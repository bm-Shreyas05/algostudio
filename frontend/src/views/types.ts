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
  annotations: Annotation[];
  state: ExecutionState;
  descriptor: ViewDescriptor;
  onSelect?: (ref: string, path?: (string | number)[]) => void;
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
