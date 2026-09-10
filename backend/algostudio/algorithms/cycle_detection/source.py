def detect_cycle(graph):
    state = {}
    for node in graph:
        state[node] = 0
    for node in graph:
        if state[node] == 0:
            if visit(graph, node, state):
                return True
    return False


def visit(graph, node, state):
    state[node] = 1
    for neighbour in graph[node]:
        if state[neighbour] == 1:
            return True
        if state[neighbour] == 0:
            if visit(graph, neighbour, state):
                return True
    state[node] = 2
    return False
