class Counter:
    def __init__(self, start=0):
        self.value = start
        self.history = []

    def bump(self, step=1):
        self.value += step
        self.history.append(self.value)
        return self.value

c = Counter(5)
c.bump()
c.bump(3)
print(c.value, c.history)
