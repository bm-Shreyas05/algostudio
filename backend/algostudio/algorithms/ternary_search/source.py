def ternary_search(arr, target):
    low = 0
    high = len(arr) - 1
    while low <= high:
        third = (high - low) // 3
        first = low + third
        second = high - third
        if arr[first] == target:
            return first
        if arr[second] == target:
            return second
        if target < arr[first]:
            high = first - 1
        elif target > arr[second]:
            low = second + 1
        else:
            low = first + 1
            high = second - 1
    return -1
