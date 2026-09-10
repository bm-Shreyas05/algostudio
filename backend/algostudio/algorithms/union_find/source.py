def union_find(pairs, size):
    parent = []
    rank = [0] * size
    for i in range(size):
        parent.append(i)
    for pair in pairs:
        union(parent, rank, pair[0], pair[1])
    roots = []
    for i in range(size):
        roots.append(find(parent, i))
    return roots


def find(parent, node):
    current = node
    while parent[current] != current:
        parent[current] = parent[parent[current]]
        current = parent[current]
    return current


def union(parent, rank, a, b):
    root_a = find(parent, a)
    root_b = find(parent, b)
    if root_a == root_b:
        return
    if rank[root_a] < rank[root_b]:
        parent[root_a] = root_b
    elif rank[root_a] > rank[root_b]:
        parent[root_b] = root_a
    else:
        parent[root_b] = root_a
        rank[root_a] += 1
