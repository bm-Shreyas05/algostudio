try:                      # `algo` is injected by AlgoStudio at run time
    algo
except NameError:         # ...and this keeps the file runnable as plain Python
    from algostudio.runtime.semantic import null as algo

import heapq

INF = float("inf")


def dijkstra(graph, source):
    dist = {}
    for node in graph:
        dist[node] = INF
    dist[source] = 0
    visited = set()
    heap = []
    heapq.heappush(heap, (0, source))
    while heap:
        pair = heapq.heappop(heap)
        d = pair[0]
        u = pair[1]
        if u in visited:
            continue
        visited.add(u)
        algo.visit(u)
        for edge in graph[u]:
            v = edge[0]
            w = edge[1]
            candidate = d + w
            improved = candidate < dist[v]
            algo.relax(u, v, w, improved)
            if improved:
                dist[v] = candidate
                heapq.heappush(heap, (candidate, v))
    return dist
