# Binary Search

**Proves:** pointer and region annotations, and branch visualization on a
three-way comparison.

The `algo.pointer` and `algo.region` calls are *optional*. Remove them and the
pointer lifter still recovers `low`, `mid` and `high` from the generic event
stream, because each is an integer variable used as a subscript index. Try it:
paste this source into the editor with the annotations deleted and compare.

**Invariant.** If the target is in the array, its index is always inside
`[low, high]`. Every iteration discards half the remaining window, so the loop
runs at most `floor(log2(n)) + 1` times.
