from __future__ import annotations

from collections.abc import Iterable, Mapping
from contextlib import contextmanager, suppress
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

from starlette.requests import Request
from structlog.contextvars import bind_contextvars, clear_contextvars, get_contextvars, reset_contextvars

from backend.core.telemetry import get_active_trace_context, parse_traceparent

REQUEST_FAILURE_KEY = "_request_failure"
CELERY_CONTEXT_HEADER_KEYS = frozenset(
    {
        "correlation_id",
        "request_id",
        "trace_id",
        "span_id",
        "traceparent",
        "user_id",
        "org_id",
        "project_id",
        "creative_id",
        "creative_version_id",
        "job_id",
        "prediction_result_id",
        "upload_session_id",
        "artifact_id",
        "modality",
    }
)
_SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "authorization",
        "api_key",
        "secret",
        "password",
        "presigned_url",
        "session_token",
        "upload_token",
        "token",
    }
)
_LARGE_CONTENT_KEY_FRAGMENTS = frozenset(
    {
        "raw_text",
        "raw_output",
        "raw_response",
        "file_content",
        "binary",
        "payload",
        "content",
        "body",
    }
)
_MAX_STRING_LENGTH = 512
_MAX_COLLECTION_ITEMS = 25


def summarize_storage_key(storage_key: str) -> str:
    parts = [part for part in storage_key.split("/") if part]
    if len(parts) <= 4:
        return storage_key
    return "/".join([*parts[:3], "...", parts[-1]])


def summarize_uri(value: str) -> str:
    if value.startswith("s3://"):
        bucket_and_key = value[5:]
        if "/" not in bucket_and_key:
            return value
        bucket_name, storage_key = bucket_and_key.split("/", 1)
        return f"s3://{bucket_name}/{summarize_storage_key(storage_key)}"

    if "://" in value:
        scheme, _, remainder = value.partition("://")
        tail = remainder.rsplit("/", 1)[-1]
        return f"{scheme}://.../{tail}" if tail else f"{scheme}://..."

    if "/" in value:
        return f".../{value.rsplit('/', 1)[-1]}"
    return value


def _is_sensitive_key(key: str) -> bool:
    return any(fragment in key for fragment in _SENSITIVE_KEY_FRAGMENTS)


def _is_large_content_key(key: str) -> bool:
    return any(fragment in key for fragment in _LARGE_CONTENT_KEY_FRAGMENTS)


def normalize_log_value(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    lower_key = (key or "").lower()

    if _is_sensitive_key(lower_key):
        return "[redacted]"

    if value is None:
        return None
    if isinstance(value, (UUID, Enum, Path)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    if isinstance(value, BaseException):
        return str(value)
    if isinstance(value, str):
        if lower_key.endswith("sha256"):
            return value[:12]
        if "storage_key" in lower_key:
            return summarize_storage_key(value)
        if lower_key.endswith("uri") or lower_key.endswith("url"):
            if "presign" in lower_key:
                return "[redacted]"
            return summarize_uri(value)
        if _is_large_content_key(lower_key):
            return {"char_count": len(value)}
        if len(value) > _MAX_STRING_LENGTH:
            return f"{value[:_MAX_STRING_LENGTH]}..."
        return value
    if isinstance(value, Mapping):
        if _is_large_content_key(lower_key):
            return {"keys": sorted(str(item) for item in value.keys())[:10], "item_count": len(value)}
        normalized: dict[str, Any] = {}
        for index, (child_key, child_value) in enumerate(value.items()):
            if index >= _MAX_COLLECTION_ITEMS:
                normalized["_truncated_items"] = len(value) - _MAX_COLLECTION_ITEMS
                break
            normalized[str(child_key)] = normalize_log_value(child_value, key=str(child_key), depth=depth + 1)
        return normalized
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        items = list(value)
        if depth >= 2:
            return {"item_count": len(items)}
        normalized_items = [
            normalize_log_value(item, key=key, depth=depth + 1)
            for item in items[:_MAX_COLLECTION_ITEMS]
        ]
        if len(items) > _MAX_COLLECTION_ITEMS:
            normalized_items.append({"_truncated_items": len(items) - _MAX_COLLECTION_ITEMS})
        return normalized_items
    return value


def normalize_log_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): normalize_log_value(value, key=str(key)) for key, value in fields.items()}


def clear_log_context() -> None:
    clear_contextvars()


def bind_log_context(**fields: Any) -> dict[str, Any]:
    safe_fields = {key: value for key, value in normalize_log_fields(fields).items() if value is not None}
    if not safe_fields:
        return {}
    return bind_contextvars(**safe_fields)


@contextmanager
def bound_log_context(**fields: Any):
    tokens = bind_log_context(**fields)
    try:
        yield
    finally:
        if tokens:
            reset_contextvars(**tokens)


def get_current_log_context() -> dict[str, Any]:
    return get_contextvars()


def get_correlation_id(default: str | None = None) -> str | None:
    with suppress(Exception):
        from asgi_correlation_id import correlation_id

        current = correlation_id.get()
        if current:
            return current
    return get_current_log_context().get("correlation_id", default)


def set_correlation_id(value: str | None) -> None:
    if not value:
        return
    with suppress(Exception):
        from asgi_correlation_id import correlation_id

        correlation_id.set(value)


def build_celery_task_headers(**fields: Any) -> dict[str, str]:
    headers: dict[str, str] = {}
    current_context = get_current_log_context()
    trace_context = get_active_trace_context()

    for key in CELERY_CONTEXT_HEADER_KEYS:
        candidate = fields.get(key)
        if candidate is None:
            candidate = current_context.get(key)
        if candidate is None:
            candidate = trace_context.get(key)
        if candidate is None:
            continue
        headers[key] = str(candidate)

    traceparent = headers.get("traceparent") or trace_context.get("traceparent")
    if traceparent:
        headers["traceparent"] = traceparent
    return headers


def extract_celery_headers(task_request: Any) -> dict[str, Any]:
    headers = getattr(task_request, "headers", None)
    if not isinstance(headers, Mapping):
        return {}
    return {str(key).lower(): value for key, value in headers.items()}


def bind_celery_task_context(
    task_request: Any,
    *,
    task_id: str | None = None,
    task_name: str | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    clear_log_context()
    headers = extract_celery_headers(task_request)
    correlation = headers.get("correlation_id") or headers.get("request_id")
    if correlation:
        set_correlation_id(str(correlation))

    parsed_trace_context = parse_traceparent(str(headers.get("traceparent"))) if headers.get("traceparent") else {}
    context_fields = {
        "correlation_id": correlation,
        "request_id": headers.get("request_id") or correlation,
        "trace_id": headers.get("trace_id") or parsed_trace_context.get("trace_id"),
        "span_id": headers.get("span_id") or parsed_trace_context.get("span_id"),
        "traceparent": headers.get("traceparent"),
        "task_id": task_id or getattr(task_request, "id", None),
        "task_name": task_name,
    }
    for key in CELERY_CONTEXT_HEADER_KEYS:
        if key in {"correlation_id", "request_id", "trace_id", "span_id", "traceparent"}:
            continue
        if key in headers:
            context_fields[key] = headers.get(key)
    context_fields.update(extra_fields)
    bind_log_context(**context_fields)
    return context_fields


def mark_request_failure(
    request: Request,
    *,
    status_code: int,
    error_type: str,
    error_message: str,
) -> None:
    setattr(
        request.state,
        REQUEST_FAILURE_KEY,
        {
            "status_code": status_code,
            "error_type": error_type,
            "error_message": error_message,
        },
    )


def consume_request_failure(scope: Mapping[str, Any]) -> dict[str, Any] | None:
    state = scope.get("state")
    if not state:
        return None
    failure = state.pop(REQUEST_FAILURE_KEY, None)
    if isinstance(failure, dict):
        return normalize_log_fields(failure)
    return None
