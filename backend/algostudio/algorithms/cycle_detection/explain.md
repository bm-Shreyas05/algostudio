# Cycle Detection

**Proves:** why the three colours are necessary. A node in state 2
has been fully explored and is safe to revisit; a node in state 1 is on the
*current path* and revisiting it is exactly a cycle. Watch the `state` table and
the call stack together -- state 1 is precisely the set of frames currently
open.
