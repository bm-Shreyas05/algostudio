# Breadth-First Search

**Proves:** the graph view is chosen from the *shape of the data*.

Nothing here declares "this is a graph". `AdjacencyMapDetector` sees a dict
whose value elements are drawn from its own key set and proposes a graph view
with high confidence; the `visited` set and the `distance` dict get their own
views by the same route. The queue panel is fed by `StackQueueLifter`, which
recognises `deque.append` / `deque.popleft` as enqueue/dequeue.

Change the input to any other adjacency map -- including one for a graph
algorithm the platform has never run -- and the same thing happens.

**Invariant.** Nodes leave the queue in non-decreasing distance order, which is
why BFS finds shortest paths in unweighted graphs.
