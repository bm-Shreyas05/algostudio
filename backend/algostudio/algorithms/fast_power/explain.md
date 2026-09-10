# Modular Exponentiation

**Proves:** logarithmic work made concrete. Exponent 45 takes six
iterations, not forty-five. The invariant is the interesting part: the product
`result * value**power` never changes, so when `power` hits zero, `result` is
the answer.
