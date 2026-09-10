def gcd(first, second):
    steps = []
    a = first
    b = second
    while b != 0:
        steps.append([a, b])
        remainder = a % b
        a = b
        b = remainder
    return [a, steps]
