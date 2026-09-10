def connected_components(graph):
    visited = set()
    components = []
    for start in graph:
        if start in visited:
            continue
        component = []
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            for neighbour in graph[node]:
                if neighbour not in visited:
                    stack.append(neighbour)
        component.sort()
        components.append(component)
    return components
