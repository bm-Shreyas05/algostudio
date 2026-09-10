class Node:
    def __init__(self, value):
        self.value = value
        self.left = None
        self.right = None


def traversals(values):
    root = None
    for value in values:
        root = insert(root, value)
    pre = []
    ino = []
    post = []
    preorder(root, pre)
    inorder(root, ino)
    postorder(root, post)
    return [pre, ino, post]


def insert(node, value):
    if node is None:
        return Node(value)
    if value < node.value:
        node.left = insert(node.left, value)
    else:
        node.right = insert(node.right, value)
    return node


def preorder(node, out):
    if node is None:
        return
    out.append(node.value)
    preorder(node.left, out)
    preorder(node.right, out)


def inorder(node, out):
    if node is None:
        return
    inorder(node.left, out)
    out.append(node.value)
    inorder(node.right, out)


def postorder(node, out):
    if node is None:
        return
    postorder(node.left, out)
    postorder(node.right, out)
    out.append(node.value)
