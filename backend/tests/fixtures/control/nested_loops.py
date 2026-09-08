pairs = []
for i in range(3):
    for j in range(3):
        if i != j:
            pairs.append((i, j))
print(len(pairs), pairs[:3])
