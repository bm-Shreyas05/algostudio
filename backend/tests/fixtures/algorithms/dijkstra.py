import heapq

def dijkstra(graph, source):
    dist = {}
    for node in graph:
        dist[node] = float("inf")
    dist[source] = 0
    visited = set()
    heap = [(0, source)]
    while heap:
        d, u = heapq.heappop(heap)
        if u in visited:
            continue
        visited.add(u)
        for v, w in graph[u]:
            candidate = d + w
            if candidate < dist[v]:
                dist[v] = candidate
                heapq.heappush(heap, (candidate, v))
    return dist

graph = {
    "A": [("B", 4), ("C", 2)],
    "B": [("D", 5)],
    "C": [("B", 1), ("D", 8)],
    "D": [],
}
print(sorted(dijkstra(graph, "A").items()))
