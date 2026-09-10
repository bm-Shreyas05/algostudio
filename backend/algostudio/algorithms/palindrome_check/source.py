def is_palindrome(text):
    cleaned = ""
    for ch in text:
        if ch.isalnum():
            cleaned += ch.lower()
    low = 0
    high = len(cleaned) - 1
    while low < high:
        if cleaned[low] != cleaned[high]:
            return False
        low += 1
        high -= 1
    return True
