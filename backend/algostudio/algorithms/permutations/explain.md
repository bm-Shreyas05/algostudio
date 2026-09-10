# Permutations

**Proves:** paired swaps. Every swap has an exact partner that
undoes it, and the swap lifter reports both -- so the timeline reads as
swap / recurse / swap-back. Stepping backwards through it is the clearest way to
see that backtracking really does restore state.
