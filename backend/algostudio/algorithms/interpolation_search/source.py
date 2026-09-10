def interpolation_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high and arr[low] <= target and target <= arr[high]:
        span = arr[high] - arr[low]
        if span == 0:
            if arr[low] == target:
                return low
            return -1
        offset = ((target - arr[low]) * (high - low)) // span
        probe = low + offset
        if arr[probe] == target:
            return probe
        if arr[probe] < target:
            low = probe + 1
        else:
            high = probe - 1
    return -1
