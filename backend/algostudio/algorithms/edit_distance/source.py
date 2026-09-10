def edit_distance(first, second):
    n = len(first)
    m = len(second)
    table = []
    for i in range(n + 1):
        table.append([0] * (m + 1))
    for i in range(n + 1):
        table[i][0] = i
    for j in range(m + 1):
        table[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if first[i - 1] == second[j - 1]:
                table[i][j] = table[i - 1][j - 1]
            else:
                best = table[i - 1][j - 1]
                if table[i - 1][j] < best:
                    best = table[i - 1][j]
                if table[i][j - 1] < best:
                    best = table[i][j - 1]
                table[i][j] = best + 1
    return table[n][m]
