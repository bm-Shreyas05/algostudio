# Knuth-Morris-Pratt

**Proves:** preprocessing as a visible phase. `build_table` runs
first and its output is an ordinary array on the heap; step through the search
loop afterwards and watch `matched` fall back along that table instead of
restarting from zero. The index `i` never moves backwards — that is the whole
point of the algorithm, and it is directly observable.
