"""Tests for thread-safe counter."""
import threading
from counter import Counter


def test_basic_increment():
    c = Counter()
    assert c.increment() == 1
    assert c.increment() == 2
    assert c.get() == 2


def test_reset():
    c = Counter()
    c.increment()
    c.increment()
    c.reset()
    assert c.get() == 0


def test_concurrent_increment():
    c = Counter()
    n_threads = 10
    n_per_thread = 100

    def worker():
        for _ in range(n_per_thread):
            c.increment()

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()

    assert c.get() == n_threads * n_per_thread, (
        f"expected {n_threads * n_per_thread}, got {c.get()} "
        "(race condition: read-modify-write not atomic)"
    )
