from __future__ import annotations

from backend.core.config import settings


def configure_telemetry() -> None:
    if not settings.otel_enabled:
        return
    try:
        import opentelemetry.trace  # noqa: F401
    except ImportError:
        return


def get_active_trace_context() -> dict[str, str]:
    try:
        from opentelemetry import trace
    except ImportError:
        return {}

    span = trace.get_current_span()
    if span is None:
        return {}

    span_context = span.get_span_context()
    if span_context is None or not span_context.is_valid:
        return {}

    trace_id = f"{span_context.trace_id:032x}"
    span_id = f"{span_context.span_id:016x}"
    trace_flags = f"{int(span_context.trace_flags):02x}"
    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "traceparent": f"00-{trace_id}-{span_id}-{trace_flags}",
    }


def parse_traceparent(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parts = value.split("-")
    if len(parts) != 4:
        return {}
    _, trace_id, span_id, _ = parts
    if len(trace_id) != 32 or len(span_id) != 16:
        return {}
    return {"trace_id": trace_id, "span_id": span_id}
