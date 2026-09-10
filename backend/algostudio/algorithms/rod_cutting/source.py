def rod_cutting(prices, length):
    best = [0] * (length + 1)
    for size in range(1, length + 1):
        for cut in range(1, size + 1):
            if cut <= len(prices):
                candidate = prices[cut - 1] + best[size - cut]
                if candidate > best[size]:
                    best[size] = candidate
    return best[length]
