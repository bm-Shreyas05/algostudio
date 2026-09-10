# Union-Find (Disjoint Set)

**Proves:** path compression as a mutation you can watch. The line
`parent[current] = parent[parent[current]]` flattens the tree *while querying
it*, and the array view shows entries being re-pointed during a `find` that was
supposed to be read-only. That side effect is the whole reason the amortised
bound holds.
