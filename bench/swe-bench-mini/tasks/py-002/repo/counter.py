"""Counter with a race condition bug."""

class Counter:
    def __init__(self):
        self._value = 0

    def increment(self):
        # BUG: read-modify-write is not atomic; two threads can both read 0
        # and both write 1, losing one increment.
        current = self._value
        self._value = current + 1
        return self._value

    def get(self):
        return self._value

    def reset(self):
        self._value = 0
