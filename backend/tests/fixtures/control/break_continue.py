found = -1
for i in range(20):
    if i % 7 == 0 and i > 0:
        found = i
        break
    if i % 2 == 0:
        continue
print("found", found)

n = 0
while True:
    n += 1
    if n > 4:
        break
print("n", n)
