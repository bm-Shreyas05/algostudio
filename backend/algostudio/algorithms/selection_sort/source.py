def selection_sort(arr):
    n = len(arr)
    for i in range(n):
        lowest = i
        for j in range(i + 1, n):
            if arr[j] < arr[lowest]:
                lowest = j
        if lowest != i:
            arr[i], arr[lowest] = arr[lowest], arr[i]
    return arr
