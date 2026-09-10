# Coin Change

**Proves:** why greedy fails and DP does not. The default coins
`[1, 5, 6, 9]` and amount 11 are chosen deliberately: greedy takes 9+1+1 = three
coins, the correct answer is 5+6 = two. Watch `best[11]` get overwritten when the
better combination is found.
