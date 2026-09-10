# Bracket Matching

**Proves:** the stack view. `stack` is a plain list, but the
push/pop lifter sees it is only ever appended to and popped from, so the stack
detector offers a stack view with the top marked -- structure inferred from use,
not declared.

Try an unbalanced string like `"([)]"` and watch it fail at the exact character.
