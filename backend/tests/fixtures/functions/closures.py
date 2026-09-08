def make_counter(start):
    count = start

    def bump(step):
        nonlocal count
        count += step
        return count

    return bump

c = make_counter(10)
print(c(1), c(2), c(3))

TOTAL = 0

def add_global(n):
    global TOTAL
    TOTAL += n

add_global(5)
add_global(7)
print(TOTAL)
