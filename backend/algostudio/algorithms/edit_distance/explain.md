# Edit Distance (Levenshtein)

**Proves:** three-way dependency. Each cell looks up, left, and
diagonally -- substitution, deletion, insertion. The three candidate reads are
separate `SUBSCRIPT_READ` events, so you can see which operation won each cell
by stepping one statement at a time.
