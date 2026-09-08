def first_divisor(n):
    for d in range(2, n):
        if n % d == 0:
            return d
    else:
        return None

print(first_divisor(15), first_divisor(13))

i = 0
while i < 3:
    i += 1
else:
    print("while-else ran", i)
