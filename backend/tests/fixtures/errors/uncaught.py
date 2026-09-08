def compute(values):
    total = 0
    for v in values:
        total += 100 // v
    return total

print(compute([5, 2, 0]))
