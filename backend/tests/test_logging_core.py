from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from backend.core.logging import _sanitize_event_dict, log_event, log_exception


class TestLoggingCore(unittest.TestCase):
    def test_sanitize_event_dict_redacts_sensitive_fields(self):
        sanitized = _sanitize_event_dict(
            None,
            "",
            {"api_key": "secret-value", "event": "demo"},
        )
        self.assertEqual(sanitized["api_key"], "[redacted]")

    def test_log_event_passes_fields_once(self):
        logger = MagicMock()
        log_event(logger, "sample_event", user_id="u1")
        logger.info.assert_called_once_with("sample_event", user_id="u1")

    def test_log_exception_includes_error_metadata(self):
        logger = MagicMock()
        exc = ValueError("bad input")
        log_exception(logger, "failed", exc, request_id="r1")
        _, kwargs = logger.error.call_args
        self.assertEqual(kwargs["error_type"], "ValueError")
        self.assertEqual(kwargs["error_message"], "bad input")
        self.assertIn("exc_info", kwargs)


if __name__ == "__main__":
    unittest.main()
