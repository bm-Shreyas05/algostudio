grid = [[0, 0, 0], [0, 0, 0]]
grid[0][1] = 5
grid[1][2] = 7
counts = {}
counts["a"] = 1
counts["a"] += 2
counts["b"] = counts.get("a", 0) * 2
print(grid, counts)
