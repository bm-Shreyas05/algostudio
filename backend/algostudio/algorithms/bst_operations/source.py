class Node:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


def bst_demo(values, target):
    root = None
    for value in values:
        root = insert(root, value)
    order = []
    inorder(root, order)
    found = search(root, target)
    return [order, found]


def insert(node, value):
    if node is None:
        return Node(value)
    if value < node.value:
        node.left = insert(node.left, value)
    elif value > node.value:
        node.right = insert(node.right, value)
    return node


def search(node, target):
    current = node
    while current is not None:
        if current.value == target:
            return True
        if target < current.value:
            current = current.left
        else:
            current = current.right
    return False


def inorder(node, out):
    if node is None:
        return
    inorder(node.left, out)
    out.append(node.value)
    inorder(node.right, out)
