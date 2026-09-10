# 0/1 Knapsack

**Proves:** the matrix view on a DP table. Each cell is filled from
cells strictly above and to the left -- step slowly and watch the dependency
pattern, which is the reason the loops go in this order and not another.
