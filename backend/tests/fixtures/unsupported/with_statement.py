class Ctx:
    def __enter__(self):
        return 42

    def __exit__(self, *args):
        return False

with Ctx() as value:
    print(value)
