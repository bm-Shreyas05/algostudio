def radix_sort(arr):
    if len(arr) == 0:
        return arr
    place = 1
    highest = max(arr)
    while highest // place > 0:
        counting_pass(arr, place)
        place *= 10
    return arr


def counting_pass(arr, place):
    counts = [0] * 10
    output = [0] * len(arr)
    for value in arr:
        digit = (value // place) % 10
        counts[digit] += 1
    for d in range(1, 10):
        counts[d] += counts[d - 1]
    for i in range(len(arr) - 1, -1, -1):
        digit = (arr[i] // place) % 10
        counts[digit] -= 1
        output[counts[digit]] = arr[i]
    for i in range(len(arr)):
        arr[i] = output[i]
