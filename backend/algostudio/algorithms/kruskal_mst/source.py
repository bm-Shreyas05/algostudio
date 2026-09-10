def kruskal(graph):
    edges = []
    seen = set()
    for u in graph:
        for edge in graph[u]:
            v = edge[0]
            weight = edge[1]
            reverse = v + "|" + u
            if reverse in seen:
                continue
            seen.add(u + "|" + v)
            edges.append([weight, u, v])
    edges.sort()
    parent = {}
    for node in graph:
        parent[node] = node
    tree = []
    total = 0
    for edge in edges:
        weight = edge[0]
        u = edge[1]
        v = edge[2]
        root_u = find(parent, u)
        root_v = find(parent, v)
        if root_u != root_v:
            parent[root_u] = root_v
            tree.append([u, v, weight])
            total += weight
    return [tree, total]


def find(parent, node):
    current = node
    while parent[current] != current:
        current = parent[current]
    return current
