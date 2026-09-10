class Node:
    def __init__(self, value):
        self.value = value
        self.next = None


def reverse_list(values):
    head = None
    for i in range(len(values) - 1, -1, -1):
        node = Node(values[i])
        node.next = head
        head = node
    previous = None
    current = head
    while current is not None:
        upcoming = current.next
        current.next = previous
        previous = current
        current = upcoming
    out = []
    node = previous
    while node is not None:
        out.append(node.value)
        node = node.next
    return out
