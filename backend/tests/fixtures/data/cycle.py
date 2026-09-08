a = [1, 2]
a.append(a)
node = {"value": 1}
node["self"] = node
print(len(a), node["value"])
