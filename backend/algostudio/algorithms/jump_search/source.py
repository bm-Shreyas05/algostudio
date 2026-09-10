import math


def jump_search(arr, target):
    n = len(arr)
    if n == 0:
        return -1
    step = int(math.sqrt(n))
    if step < 1:
        step = 1
    prev = 0
    current = step
    while current < n and arr[current - 1] < target:
        prev = current
        current += step
    limit = current
    if limit > n:
        limit = n
    for i in range(prev, limit):
        if arr[i] == target:
            return i
    return -1
