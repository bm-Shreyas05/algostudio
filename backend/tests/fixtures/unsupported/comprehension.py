squares = [n * n for n in range(6)]
evens = {n for n in range(10) if n % 2 == 0}
lookup = {n: n * n for n in range(4)}
gen = (n for n in range(3))
print(squares, sorted(evens), lookup, sum(gen))
