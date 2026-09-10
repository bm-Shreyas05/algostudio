# Fibonacci (memoised)

**Proves:** memoisation as a shape you can see. The call tree is
lopsided -- the left spine descends all the way down and every right branch
terminates immediately on a cache hit. Compare `function_calls` against the
un-memoised version in the fixtures: 23 calls instead of 465 for n=12.
