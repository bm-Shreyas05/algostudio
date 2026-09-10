# Subset Sum

**Proves:** pruning. The `remaining < 0` guard cuts whole subtrees,
and the call tree shows those branches stopping short. Compare the actual
`function_calls` count against 2^n -- the gap is what pruning bought.

`chosen` is a stack: the push/pop lifter reports the append and the pop as
structural operations without being told the list is a stack.
