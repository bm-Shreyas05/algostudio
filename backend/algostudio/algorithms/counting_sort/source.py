def counting_sort(arr):
    if len(arr) == 0:
        return arr
    highest = max(arr)
    counts = [0] * (highest + 1)
    for value in arr:
        counts[value] += 1
    position = 0
    for value in range(len(counts)):
        remaining = counts[value]
        while remaining > 0:
            arr[position] = value
            position += 1
            remaining -= 1
    return arr
