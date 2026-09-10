def fibonacci(n):
    memo = {}
    return fib(n, memo)


def fib(n, memo):
    if n <= 1:
        return n
    if n in memo:
        return memo[n]
    result = fib(n - 1, memo) + fib(n - 2, memo)
    memo[n] = result
    return result
