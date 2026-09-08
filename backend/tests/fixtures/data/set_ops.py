s = {1, 2, 3}
s.add(4)
s.discard(1)
t = {3, 4, 5}
print(sorted(s), sorted(s & t), sorted(s | t), sorted(s - t))
