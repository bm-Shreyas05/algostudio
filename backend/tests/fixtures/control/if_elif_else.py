def classify(n):
    if n < 0:
        return "negative"
    elif n == 0:
        return "zero"
    elif n < 10:
        return "small"
    else:
        return "large"

for value in [-5, 0, 3, 42]:
    print(value, classify(value))
