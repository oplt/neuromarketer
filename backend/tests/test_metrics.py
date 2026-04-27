from __future__ import annotations

import threading
import unittest

from backend.core.metrics import MetricsRegistry


class TestMetricsRegistry(unittest.TestCase):
    def test_counter_rendering(self):
        registry = MetricsRegistry()
        registry.increment("requests_total", labels={"route": "/health"})
        output = registry.render_prometheus()
        self.assertIn("# TYPE requests_total counter", output)
        self.assertIn('requests_total{route="/health"} 1.0', output)

    def test_summary_rendering(self):
        registry = MetricsRegistry()
        registry.observe("request_duration_seconds", 0.2, labels={"route": "/health"})
        output = registry.render_prometheus()
        self.assertIn("# TYPE request_duration_seconds summary", output)
        self.assertIn('request_duration_seconds_count{route="/health"} 1.0', output)
        self.assertIn('request_duration_seconds_sum{route="/health"} 0.2', output)

    def test_labels_are_escaped(self):
        registry = MetricsRegistry()
        registry.increment("events_total", labels={"msg": 'line1\nline2"q"\\x'})
        output = registry.render_prometheus()
        self.assertIn('msg="line1\\nline2\\"q\\"\\\\x"', output)

    def test_concurrent_increment_and_render_do_not_crash(self):
        registry = MetricsRegistry()
        errors: list[BaseException] = []

        def writer():
            try:
                for _ in range(500):
                    registry.increment("jobs_total", labels={"queue": "q1"})
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer) for _ in range(4)]
        for thread in threads:
            thread.start()
        for _ in range(20):
            registry.render_prometheus()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
