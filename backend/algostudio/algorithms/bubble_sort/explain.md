# Bubble Sort

**Proves:** semantic events can be recovered from code nobody annotated.

This is the most important plugin in the set, precisely because it is the least
interesting algorithm. There are no `algo.*` calls. The `SWAP` events you see in
the timeline were produced by `SwapLifter`, which matched a structural pattern:
two subscript writes to the same container, at different indices, within one
statement, whose values exchange. It has never heard of bubble sort, and it
fires the same way on a partition step in quick sort or on a student's own code.

**Invariant.** After pass `i`, the last `i` elements are in their final places.
