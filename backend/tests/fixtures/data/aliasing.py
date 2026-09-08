a = [1, 2, 3]
b = a
b.append(4)
c = a[:]
c.append(5)
print(a, b, c, a is b, a is c)
nested = {"xs": a}
nested["xs"].append(6)
print(a)
