from __future__ import annotations

import unittest

from backend.core.log_context import _MAX_COLLECTION_ITEMS, normalize_log_value


class TestLogContext(unittest.TestCase):
    def test_generator_is_bounded_to_max_items_plus_one(self):
        consumed: list[int] = []

        def values():
            for index in range(10_000):
                consumed.append(index)
                yield index

        normalized = normalize_log_value(values())
        self.assertIsInstance(normalized, list)
        self.assertEqual(len(consumed), _MAX_COLLECTION_ITEMS + 1)
        self.assertEqual(normalized[-1], {"_truncated_items": "unknown"})

    def test_deep_iterable_uses_bounded_summary_without_len(self):
        consumed: list[int] = []

        def values():
            for index in range(10_000):
                consumed.append(index)
                yield index

        normalized = normalize_log_value(values(), depth=2)
        self.assertEqual(
            normalized,
            {"item_count": "unknown", "sample_count": _MAX_COLLECTION_ITEMS},
        )
        self.assertEqual(len(consumed), _MAX_COLLECTION_ITEMS + 1)


if __name__ == "__main__":
    unittest.main()
