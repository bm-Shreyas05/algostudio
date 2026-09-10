def bracket_matcher(text):
    stack = []
    pairs = {}
    pairs[")"] = "("
    pairs["]"] = "["
    pairs["}"] = "{"
    for ch in text:
        if ch == "(" or ch == "[" or ch == "{":
            stack.append(ch)
        elif ch in pairs:
            if len(stack) == 0:
                return False
            top = stack.pop()
            if top != pairs[ch]:
                return False
    return len(stack) == 0
