def apply_twice(fn, value):
    return fn(fn(value))

double = lambda v: v * 2
print(apply_twice(double, 3))
print(sorted([3, 1, 2], key=lambda v: -v))
