# Bellman-Ford

**Proves:** the relax lifter firing on code that is not Dijkstra.
`RelaxLifter` matches any conditional improvement of a keyed distance -- it has
never heard of either algorithm, and it reports the same `relax` events here.

The `changed` flag is worth watching: on most graphs the algorithm converges long
before its V-1 worst case, and the early break makes that visible.
