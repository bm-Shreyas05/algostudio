xs = [1, 2, 3]
try:
    print(xs[10])
except IndexError as exc:
    print("caught", type(exc).__name__)
try:
    d = {}
    print(d["missing"])
except KeyError:
    print("caught KeyError")
