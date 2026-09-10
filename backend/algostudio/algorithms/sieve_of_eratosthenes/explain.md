# Sieve of Eratosthenes

**Proves:** a boolean array as a visualization. The array view
shows the sieve filling in, and the inner loop starting at `p*p` rather than
`2*p` is visible as a jump — that optimisation is the difference between
O(n log log n) and O(n log n), and you can watch it happen.
