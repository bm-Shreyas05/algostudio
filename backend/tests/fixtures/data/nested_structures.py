graph = {"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []}
matrix = [[1, 2], [3, 4]]
records = [{"id": 1, "tags": {"x"}}, {"id": 2, "tags": {"y", "z"}}]
matrix[1][0] = 30
graph["A"].append("D")
print(graph, matrix, len(records))
