def describe(a, b=2, *rest, key="k", **extra):
    return (a, b, rest, key, sorted(extra.items()))

print(describe(1))
print(describe(1, 3, 4, 5, key="z", other=9))
