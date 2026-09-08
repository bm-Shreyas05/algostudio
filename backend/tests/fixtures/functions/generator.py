def countdown(n):
    while n > 0:
        yield n
        n -= 1

total = 0
for v in countdown(4):
    total += v
print(total)
