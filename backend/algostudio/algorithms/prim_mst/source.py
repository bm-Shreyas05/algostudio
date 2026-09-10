import heapq


def prim(graph, start):
    visited = set()
    tree = []
    total = 0
    heap = []
    visited.add(start)
    for edge in graph[start]:
        heapq.heappush(heap, (edge[1], start, edge[0]))
    while heap:
        item = heapq.heappop(heap)
        weight = item[0]
        source = item[1]
        target = item[2]
        if target in visited:
            continue
        visited.add(target)
        tree.append([source, target, weight])
        total += weight
        for edge in graph[target]:
            if edge[0] not in visited:
                heapq.heappush(heap, (edge[1], target, edge[0]))
    return [tree, total]
