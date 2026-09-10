def knapsack(weights, values, capacity):
    n = len(weights)
    table = []
    for i in range(n + 1):
        row = [0] * (capacity + 1)
        table.append(row)
    for i in range(1, n + 1):
        for c in range(capacity + 1):
            without = table[i - 1][c]
            if weights[i - 1] <= c:
                with_item = values[i - 1] + table[i - 1][c - weights[i - 1]]
                if with_item > without:
                    table[i][c] = with_item
                else:
                    table[i][c] = without
            else:
                table[i][c] = without
    return table[n][capacity]
