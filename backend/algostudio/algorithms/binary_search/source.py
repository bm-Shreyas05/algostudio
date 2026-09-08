try:                      # `algo` is injected by AlgoStudio at run time
    algo
except NameError:         # ...and this keeps the file runnable as plain Python
    from algostudio.runtime.semantic import null as algo


def binary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        algo.region(arr, low, high, "search window")
        mid = (low + high) // 2
        algo.pointer(arr, mid, "mid")
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            low = mid + 1
        else:
            high = mid - 1
    return -1
