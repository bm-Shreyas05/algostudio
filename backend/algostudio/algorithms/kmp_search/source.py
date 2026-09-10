def kmp_search(text, pattern):
    if len(pattern) == 0:
        return 0
    table = build_table(pattern)
    matched = 0
    for i in range(len(text)):
        while matched > 0 and text[i] != pattern[matched]:
            matched = table[matched - 1]
        if text[i] == pattern[matched]:
            matched += 1
        if matched == len(pattern):
            return i - matched + 1
    return -1


def build_table(pattern):
    table = [0] * len(pattern)
    length = 0
    for i in range(1, len(pattern)):
        while length > 0 and pattern[i] != pattern[length]:
            length = table[length - 1]
        if pattern[i] == pattern[length]:
            length += 1
        table[i] = length
    return table
