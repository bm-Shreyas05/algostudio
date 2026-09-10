def is_anagram(first, second):
    counts = {}
    for ch in first:
        if ch in counts:
            counts[ch] += 1
        else:
            counts[ch] = 1
    for ch in second:
        if ch not in counts:
            return False
        counts[ch] -= 1
        if counts[ch] == 0:
            del counts[ch]
    return len(counts) == 0
