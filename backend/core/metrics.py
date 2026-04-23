from __future__ import annotations

from collections import defaultdict
from threading import Lock


def _normalize_labels(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not labels:
        return ()
    return tuple(sorted((key, value) for key, value in labels.items()))


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: defaultdict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(
            float
        )
        self._summaries: defaultdict[tuple[str, tuple[tuple[str, str], ...]], dict[str, float]] = (
            defaultdict(lambda: {"count": 0.0, "sum": 0.0})
        )

    def increment(
        self, name: str, *, value: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        key = (name, _normalize_labels(labels))
        with self._lock:
            self._counters[key] += value

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = (name, _normalize_labels(labels))
        with self._lock:
            self._summaries[key]["count"] += 1.0
            self._summaries[key]["sum"] += value

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                label_text = _format_labels(labels)
                lines.append(f"# TYPE {name} counter")
                lines.append(f"{name}{label_text} {value}")
            for (name, labels), summary in sorted(self._summaries.items()):
                label_text = _format_labels(labels)
                lines.append(f"# TYPE {name} summary")
                lines.append(f"{name}_count{label_text} {summary['count']}")
                lines.append(f"{name}_sum{label_text} {summary['sum']}")
        return "\n".join(lines) + ("\n" if lines else "")


def _format_labels(labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return ""
    formatted = ",".join(f'{key}="{value}"' for key, value in labels)
    return f"{{{formatted}}}"


metrics = MetricsRegistry()
