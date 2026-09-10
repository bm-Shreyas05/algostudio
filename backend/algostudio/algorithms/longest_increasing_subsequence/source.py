def longest_increasing_subsequence(arr):
    n = len(arr)
    if n == 0:
        return 0
    best = [1] * n
    for i in range(1, n):
        for j in range(i):
            if arr[j] < arr[i] and best[j] + 1 > best[i]:
                best[i] = best[j] + 1
    longest = 0
    for value in best:
        if value > longest:
            longest = value
    return longest
