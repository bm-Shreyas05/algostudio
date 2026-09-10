def lcs(first, second):
    n = len(first)
    m = len(second)
    table = []
    for i in range(n + 1):
        table.append([0] * (m + 1))
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if first[i - 1] == second[j - 1]:
                table[i][j] = table[i - 1][j - 1] + 1
            elif table[i - 1][j] >= table[i][j - 1]:
                table[i][j] = table[i - 1][j]
            else:
                table[i][j] = table[i][j - 1]
    out = ""
    i = n
    j = m
    while i > 0 and j > 0:
        if first[i - 1] == second[j - 1]:
            out = first[i - 1] + out
            i -= 1
            j -= 1
        elif table[i - 1][j] >= table[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return out
