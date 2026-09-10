# Quick Sort

**Proves:** swap lifting inside a recursive algorithm, and the call
tree for a divide-and-conquer split that is *uneven* (unlike merge sort).

Watch the pivot: everything the partition loop touches ends up on one side of
`boundary`. The worst case (already-sorted input) is visible as a call tree that
degenerates into a chain — try running it on a sorted array and compare.
