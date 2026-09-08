xs = [3, 1, 4, 1, 5]
xs.append(9)
xs.insert(0, 2)
xs.remove(1)
last = xs.pop()
xs.sort()
xs.reverse()
xs.extend([7, 8])
print(xs, last, xs.index(4), xs.count(1))
