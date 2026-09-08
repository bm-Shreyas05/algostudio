d = {"a": 1}
d["b"] = 2
d.update({"c": 3})
d.setdefault("d", 4)
value = d.pop("a")
print(sorted(d.items()), value, "b" in d, len(d))
