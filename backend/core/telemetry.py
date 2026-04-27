from __future__ import annotations

import logging
import re

from backend.core.config import settings

logger = logging.getLogger(__name__)
_TRACEPARENT_RE = re.compile(r"^[0-9a-f]+$")
_TELEMETRY_CONFIGURED = False


def configure_telemetry() -> None:
    global _TELEMETRY_CONFIGURED
    if not settings.otel_enabled:
        return
    if _TELEMETRY_CONFIGURED:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        logger.warning(
            "telemetry_config_skipped",
            extra={"reason": "opentelemetry_packages_missing"},
        )
        return
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": settings.otel_service_name or settings.service_name,
            }
        )
    )
    endpoint = settings.otel_exporter_otlp_endpoint
    if endpoint:
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _TELEMETRY_CONFIGURED = True


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
    version, trace_id, span_id, flags = parts
    if version != "00":
        return {}
    if len(trace_id) != 32 or len(span_id) != 16 or len(flags) != 2:
        return {}
    if not (_TRACEPARENT_RE.fullmatch(trace_id) and _TRACEPARENT_RE.fullmatch(span_id)):
        return {}
    if not _TRACEPARENT_RE.fullmatch(flags):
        return {}
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return {}
    return {"trace_id": trace_id, "span_id": span_id}
