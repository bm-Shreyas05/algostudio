def max_subarray(arr):
    best = arr[0]
    current = arr[0]
    start = 0
    best_start = 0
    best_end = 0
    for i in range(1, len(arr)):
        if current + arr[i] < arr[i]:
            current = arr[i]
            start = i
        else:
            current = current + arr[i]
        if current > best:
            best = current
            best_start = start
            best_end = i
    return [best, best_start, best_end]
