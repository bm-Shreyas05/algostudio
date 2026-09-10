# Floyd-Warshall

**Proves:** a triple-nested loop rendered as a table that fills in.
The static analysis panel flags loop-nesting depth 3 before you run it, and the
statement count in the analytics confirms the V^3 growth if you re-run on a
larger graph.

The outer variable `k` is the whole algorithm: it is the *set of allowed
intermediate nodes*, growing by one each pass.
