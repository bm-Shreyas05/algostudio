# Kruskal's Minimum Spanning Tree

**Proves:** `list.sort()` -- a C-level mutation that per-element
probes cannot see. The method probe snapshots the list before and after and emits
a single `OBJECT_MUTATED`, so the array view jumps straight to sorted order and
stepping backwards restores it exactly. That is the escape hatch described in
docs/02 §H.2 doing real work.

The `parent` table is the interesting object: watch nodes get re-pointed as
components merge.
