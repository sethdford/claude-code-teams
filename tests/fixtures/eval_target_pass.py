"""Target: simple add() function with passing tests."""

def add(a, b):
    if a is None or b is None:
        raise TypeError("add requires non-None inputs")
    return a + b
