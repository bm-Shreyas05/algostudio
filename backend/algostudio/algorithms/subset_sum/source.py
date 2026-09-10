def subset_sum(numbers, target):
    chosen = []
    found = []
    search(numbers, 0, target, chosen, found)
    return found


def search(numbers, index, remaining, chosen, found):
    if remaining == 0:
        found.append(list(chosen))
        return
    if index >= len(numbers):
        return
    if remaining < 0:
        return
    chosen.append(numbers[index])
    search(numbers, index + 1, remaining - numbers[index], chosen, found)
    chosen.pop()
    search(numbers, index + 1, remaining, chosen, found)
