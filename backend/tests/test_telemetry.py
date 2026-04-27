from __future__ import annotations

import unittest

from backend.core.telemetry import parse_traceparent


class TestTelemetry(unittest.TestCase):
    def test_parse_traceparent_valid(self):
        value = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        parsed = parse_traceparent(value)
        self.assertEqual(parsed["trace_id"], "4bf92f3577b34da6a3ce929d0e0e4736")
        self.assertEqual(parsed["span_id"], "00f067aa0ba902b7")

    def test_parse_traceparent_rejects_invalid(self):
        invalid_values = [
            None,
            "",
            "00-xyz-00f067aa0ba902b7-01",
            "00-00000000000000000000000000000000-00f067aa0ba902b7-01",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-0000000000000000-01",
            "ff-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-zz",
        ]
        for value in invalid_values:
            with self.subTest(value=value):
                self.assertEqual(parse_traceparent(value), {})


if __name__ == "__main__":
    unittest.main()
