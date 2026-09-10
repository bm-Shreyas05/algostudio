def rabin_karp(text, pattern):
    n = len(text)
    m = len(pattern)
    if m == 0 or m > n:
        return -1
    base = 256
    modulus = 101
    target = 0
    window = 0
    power = 1
    for i in range(m - 1):
        power = (power * base) % modulus
    for i in range(m):
        target = (base * target + ord(pattern[i])) % modulus
        window = (base * window + ord(text[i])) % modulus
    for i in range(n - m + 1):
        if window == target:
            if matches(text, pattern, i):
                return i
        if i < n - m:
            window = (base * (window - ord(text[i]) * power) + ord(text[i + m])) % modulus
            if window < 0:
                window += modulus
    return -1


def matches(text, pattern, offset):
    for j in range(len(pattern)):
        if text[offset + j] != pattern[j]:
            return False
    return True
