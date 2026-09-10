def prime_factors(number):
    factors = []
    remaining = number
    divisor = 2
    while divisor * divisor <= remaining:
        while remaining % divisor == 0:
            factors.append(divisor)
            remaining = remaining // divisor
        divisor += 1
    if remaining > 1:
        factors.append(remaining)
    return factors
