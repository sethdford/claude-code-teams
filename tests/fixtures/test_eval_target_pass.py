"""Tests for eval_target_pass.add()."""
import sys
import unittest

sys.path.insert(0, ".")
from eval_target_pass import add


class AddTests(unittest.TestCase):
    def test_returns_sum(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(add(-1, 1), 0)

    def test_rejects_none(self):
        with self.assertRaises(TypeError):
            add(None, 1)
        with self.assertRaises(TypeError):
            add(1, None)


if __name__ == "__main__":
    unittest.main()
