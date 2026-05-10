"""Tests for pagination.next_page."""
import pytest
from pagination import next_page


def test_first_page():
    items = list(range(25))
    assert next_page(items, 0, 10) == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]


def test_middle_page():
    items = list(range(25))
    assert next_page(items, 1, 10) == [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]


def test_last_partial_page():
    items = list(range(25))
    assert next_page(items, 2, 10) == [20, 21, 22, 23, 24]


def test_exact_boundary():
    """Bug: when total is exactly divisible by page_size, last page should be full."""
    items = list(range(20))
    assert next_page(items, 1, 10) == [10, 11, 12, 13, 14, 15, 16, 17, 18, 19]


def test_past_end():
    items = list(range(10))
    assert next_page(items, 5, 10) == []


def test_rejects_negative_index():
    with pytest.raises(ValueError):
        next_page([1, 2, 3], -1, 10)


def test_rejects_zero_page_size():
    with pytest.raises(ValueError):
        next_page([1, 2, 3], 0, 0)


def test_rejects_negative_page_size():
    with pytest.raises(ValueError):
        next_page([1, 2, 3], 0, -5)
