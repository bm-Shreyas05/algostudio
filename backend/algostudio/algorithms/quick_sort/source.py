def quick_sort(arr):
    sort_range(arr, 0, len(arr) - 1)
    return arr


def sort_range(arr, lo, hi):
    if lo >= hi:
        return
    split = partition(arr, lo, hi)
    sort_range(arr, lo, split - 1)
    sort_range(arr, split + 1, hi)


def partition(arr, lo, hi):
    pivot = arr[hi]
    boundary = lo - 1
    for j in range(lo, hi):
        if arr[j] <= pivot:
            boundary += 1
            arr[boundary], arr[j] = arr[j], arr[boundary]
    arr[boundary + 1], arr[hi] = arr[hi], arr[boundary + 1]
    return boundary + 1
