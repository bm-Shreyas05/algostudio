# Longest Common Subsequence

**Proves:** two phases over one structure. The table fills forward,
then `i` and `j` walk it backwards to reconstruct the answer -- the same matrix,
read in the opposite direction. The traceback is where students usually lose the
thread, and stepping through it is exactly what the tool is for.
