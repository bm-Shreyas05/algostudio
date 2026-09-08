import type { ComponentType } from "react";
import { ArrayView } from "./ArrayView";
import { GraphView } from "./GraphView";
import { HeapView, LinkedListView, QueueView, StackView } from "./QueueView";
import { MatrixView, ObjectView, SetView, TableView, ValueView } from "./TableView";
import { TreeView } from "./TreeView";
import type { ViewProps } from "./types";

/**
 * The view registry.
 *
 * Keyed by *structural view name*, never by algorithm. Adding a data-structure
 * view means adding an entry here plus a detector on the backend -- two
 * registry edits and no changes to any panel (docs/07 §M.6).
 */
export const VIEW_REGISTRY: Record<string, ComponentType<ViewProps>> = {
  array: ArrayView,
  matrix: MatrixView,
  graph: GraphView,
  tree: TreeView,
  "linked-list": LinkedListView,
  table: TableView,
  set: SetView,
  queue: QueueView,
  stack: StackView,
  heap: HeapView,
  object: ObjectView,
  value: ValueView,
};

export function resolveView(name: string): ComponentType<ViewProps> {
  return VIEW_REGISTRY[name] ?? ValueView;
}

export const VIEW_LABELS: Record<string, string> = {
  array: "Array", matrix: "Matrix", graph: "Graph", tree: "Tree",
  "linked-list": "Linked list", table: "Table", set: "Set", queue: "Queue",
  stack: "Stack", heap: "Heap", object: "Object", value: "Raw",
};
