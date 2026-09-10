INF = float("inf")


def bellman_ford(graph, source):
    dist = {}
    for node in graph:
        dist[node] = INF
    dist[source] = 0
    passes = len(graph) - 1
    for _ in range(passes):
        changed = False
        for u in graph:
            if dist[u] == INF:
                continue
            for edge in graph[u]:
                v = edge[0]
                weight = edge[1]
                candidate = dist[u] + weight
                if candidate < dist[v]:
                    dist[v] = candidate
                    changed = True
        if not changed:
            break
    return dist
