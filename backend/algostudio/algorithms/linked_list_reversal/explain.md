# Linked List Reversal

**Proves:** pointer surgery, drawn. The linked-list view follows
`next` from the head, so you watch arrows flip one at a time. The three-variable
dance (`previous`, `current`, `upcoming`) is the bit everyone gets wrong from a
textbook, and here each variable is a labelled thing on screen.

`upcoming` exists solely because overwriting `current.next` would otherwise lose
the rest of the list -- step one line at a time and the necessity is obvious.
