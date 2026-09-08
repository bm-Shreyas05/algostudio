words = ["alpha", "beta", "gamma"]
for w in words:
    print(w.upper())
scores = {"a": 1, "b": 2}
for key in scores:
    print(key, scores[key])
for i, w in enumerate(words):
    print(i, w)
for a, b in zip([1, 2], [3, 4]):
    print(a + b)
for ch in "xyz":
    print(ch)
