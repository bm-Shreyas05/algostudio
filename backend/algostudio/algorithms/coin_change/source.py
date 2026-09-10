def coin_change(coins, amount):
    unreachable = amount + 1
    best = [unreachable] * (amount + 1)
    best[0] = 0
    for value in range(1, amount + 1):
        for coin in coins:
            if coin <= value:
                candidate = best[value - coin] + 1
                if candidate < best[value]:
                    best[value] = candidate
    if best[amount] == unreachable:
        return -1
    return best[amount]
