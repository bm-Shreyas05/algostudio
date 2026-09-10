INF = float("inf")


def floyd_warshall(graph):
    nodes = list(graph)
    dist = {}
    for a in nodes:
        row = {}
        for b in nodes:
            if a == b:
                row[b] = 0
            else:
                row[b] = INF
        dist[a] = row
    for u in graph:
        for edge in graph[u]:
            dist[u][edge[0]] = edge[1]
    for k in nodes:
        for i in nodes:
            for j in nodes:
                through = dist[i][k] + dist[k][j]
                if through < dist[i][j]:
                    dist[i][j] = through
    return dist
