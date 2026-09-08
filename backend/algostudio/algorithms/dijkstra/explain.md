# Dijkstra's Shortest Path

**Proves:** heterogeneous simultaneous views, and that a hint biases rather than
forces view selection.

Three views appear at once and are kept in sync by the timeline: the graph
(from the adjacency detector), the distance table (from the mapping detector),
and the priority queue (from the heap detector, which requires *both* the heap
property to hold *and* the list to have been mutated by heap operations -- a
list that merely happens to be heap-ordered is not a heap).

The `viz_hints` in `plugin.py` add at most 0.3 to a view's score and only to
views a detector already proposed. Delete them and the same three views are
selected; they only break ties.

`algo.visit` and `algo.relax` are explicit here, but `RelaxLifter` recovers
relaxations from un-annotated code too -- it matches any conditional
improvement of a keyed distance, which is why it also fires inside Bellman-Ford
and in dynamic-programming code that has nothing to do with graphs.

**Invariant.** Once a node is popped, its distance is final. This is what fails
when edge weights can be negative.
