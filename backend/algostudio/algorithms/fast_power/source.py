def fast_power(base, exponent, modulus):
    result = 1
    value = base % modulus
    power = exponent
    while power > 0:
        if power % 2 == 1:
            result = (result * value) % modulus
        power = power // 2
        value = (value * value) % modulus
    return result
