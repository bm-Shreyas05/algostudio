def permutations(items):
    result = []
    working = list(items)
    generate(working, 0, result)
    return result


def generate(items, start, result):
    if start == len(items) - 1:
        result.append(list(items))
        return
    for i in range(start, len(items)):
        items[start], items[i] = items[i], items[start]
        generate(items, start + 1, result)
        items[start], items[i] = items[i], items[start]
