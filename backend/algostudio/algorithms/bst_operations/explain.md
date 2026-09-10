# Binary Search Tree

**Proves:** the tree view, derived with no help. The
`LinkedStructureDetector` sees `Node` objects whose `left`/`right` fields point
at more `Node` objects and proposes a tree -- it is matching on the shape of the
heap, not on the class name.

Try inserting an already-sorted list and watch the tree degenerate into a
chain: that is the O(n) worst case, drawn.
