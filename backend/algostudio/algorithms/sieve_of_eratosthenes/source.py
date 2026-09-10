def sieve(limit):
    flags = [True] * (limit + 1)
    flags[0] = False
    if limit >= 1:
        flags[1] = False
    p = 2
    while p * p <= limit:
        if flags[p]:
            multiple = p * p
            while multiple <= limit:
                flags[multiple] = False
                multiple += p
        p += 1
    primes = []
    for value in range(limit + 1):
        if flags[value]:
            primes.append(value)
    return primes
