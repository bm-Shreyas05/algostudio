# Merge Sort

**Proves:** a divide-and-conquer algorithm needs no special support.

There is not a single `algo.*` call in this source, and no merge-sort-specific
code anywhere in the platform. The recursion tree comes from `FUNCTION_ENTERED`
and `FUNCTION_EXITED` events via the generic call-tree view; the sub-array
slices are ordinary heap objects that the scalar-array detector recognises; the
comparison count comes from comparison events.

**Invariant.** Every recursive call returns a sorted list, so `merge` only ever
combines two sorted inputs.
