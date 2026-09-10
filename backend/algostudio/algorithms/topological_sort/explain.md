# Topological Sort

**Proves:** a counter table driving a queue. The default input is a
getting-dressed dependency graph -- socks before shoes, shirt before tie. Watch
`indegree` count down in the table view and a node pop into the queue the moment
it hits zero.

The cycle check at the end is the same algorithm answering a different question:
if anything is left with a non-zero indegree, no valid order exists.
