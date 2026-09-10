# N-Queens

**Proves:** backtracking as an observable act. `board[row] = -1`
after the recursive call is the undo, and the array view shows the queen being
lifted back off. The call tree is the search tree -- every branch that dead-ends
is a subtree that terminates early.
