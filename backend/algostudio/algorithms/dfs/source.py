def dfs(graph, start):
    visited = set()
    order = []
    stack = [start]
    while stack:
        node = stack.pop()
        if node in visited:
            continue
        visited.add(node)
        order.append(node)
        neighbours = graph[node]
        for i in range(len(neighbours) - 1, -1, -1):
            if neighbours[i] not in visited:
                stack.append(neighbours[i])
    return order
