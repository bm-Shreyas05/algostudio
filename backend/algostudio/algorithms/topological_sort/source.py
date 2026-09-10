from collections import deque


def topological_sort(graph):
    indegree = {}
    for node in graph:
        indegree[node] = 0
    for node in graph:
        for neighbour in graph[node]:
            indegree[neighbour] += 1
    queue = deque()
    for node in indegree:
        if indegree[node] == 0:
            queue.append(node)
    order = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in graph[node]:
            indegree[neighbour] -= 1
            if indegree[neighbour] == 0:
                queue.append(neighbour)
    if len(order) < len(graph):
        return []
    return order
