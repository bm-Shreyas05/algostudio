def heap_sort(arr):
    n = len(arr)
    start = n // 2 - 1
    for i in range(start, -1, -1):
        sift_down(arr, n, i)
    for end in range(n - 1, 0, -1):
        arr[0], arr[end] = arr[end], arr[0]
        sift_down(arr, end, 0)
    return arr


def sift_down(arr, size, root):
    largest = root
    left = 2 * root + 1
    right = 2 * root + 2
    if left < size and arr[left] > arr[largest]:
        largest = left
    if right < size and arr[right] > arr[largest]:
        largest = right
    if largest != root:
        arr[root], arr[largest] = arr[largest], arr[root]
        sift_down(arr, size, largest)
