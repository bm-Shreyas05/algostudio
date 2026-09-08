from collections import deque


def bfs(graph, start):
    visited = set()
    order = []
    distance = {}
    queue = deque()
    queue.append(start)
    visited.add(start)
    distance[start] = 0
    while queue:
        node = queue.popleft()
        order.append(node)
        for neighbour in graph[node]:
            if neighbour not in visited:
                visited.add(neighbour)
                distance[neighbour] = distance[node] + 1
                queue.append(neighbour)
    return order
