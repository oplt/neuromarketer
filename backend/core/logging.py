from __future__ import annotations

import sys
import json
import logging
from logging.config import dictConfig
from pathlib import Path
from typing import Any

import structlog

from backend.core.config import settings
from backend.core.log_context import (
    normalize_log_fields,
    normalize_log_value,
    summarize_storage_key,
)
from backend.core.telemetry import get_active_trace_context

_LOGGING_CONFIGURED = False


class MaxLevelFilter(logging.Filter):
    def __init__(self, name: str = "", *, max_level: int | str = logging.INFO) -> None:
        super().__init__(name)
        if isinstance(max_level, str):
            self.max_level = logging._nameToLevel.get(max_level.upper(), logging.INFO)
        else:
            self.max_level = int(max_level)

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def _resolve_log_format() -> str:
    if settings.log_format != "auto":
        return settings.log_format
    return "json" if settings.app_env in {"staging", "production"} else "pretty"


def _coerce_legacy_event_dict(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    legacy_extra = event_dict.pop("extra", None)
    if isinstance(legacy_extra, dict):
        legacy_event = legacy_extra.get("event")
        if legacy_event and event_dict.get("event"):
            event_dict["event"] = normalize_log_value(legacy_event, key="event")

        extra_fields = legacy_extra.get("extra_fields")
        if isinstance(extra_fields, dict):
            event_dict.update(normalize_log_fields(extra_fields))

    record = event_dict.get("_record")
    if record is not None:
        record_event = getattr(record, "event", None)
        if record_event and event_dict.get("event"):
            event_dict["event"] = normalize_log_value(record_event, key="event")

        record_extra_fields = getattr(record, "extra_fields", None)
        if isinstance(record_extra_fields, dict):
            event_dict.update(normalize_log_fields(record_extra_fields))

    return event_dict


def _add_service_metadata(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.setdefault("service", settings.service_name)
    event_dict.setdefault("environment", settings.app_env)
    return event_dict


def _add_trace_metadata(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    if event_dict.get("trace_id") and event_dict.get("span_id"):
        return event_dict

    trace_context = get_active_trace_context()
    if trace_context:
        event_dict.setdefault("trace_id", trace_context.get("trace_id"))
        event_dict.setdefault("span_id", trace_context.get("span_id"))
        event_dict.setdefault("traceparent", trace_context.get("traceparent"))
    return event_dict


def _add_error_metadata(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    exc_info = event_dict.get("exc_info")
    if exc_info:
        if exc_info is True:
            exc_info = None
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            exc_type, exc, _ = exc_info
            if exc_type is not None:
                event_dict.setdefault("error_type", getattr(exc_type, "__name__", str(exc_type)))
            if exc is not None:
                event_dict.setdefault("error_message", str(exc))

    error = event_dict.get("error")
    if isinstance(error, BaseException):
        event_dict.setdefault("error_type", error.__class__.__name__)
        event_dict.setdefault("error_message", str(error))
    return event_dict


def _sanitize_event_dict(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    metadata = {key: value for key, value in event_dict.items() if key.startswith("_")}
    payload = {key: value for key, value in event_dict.items() if not key.startswith("_")}
    payload = normalize_log_fields(payload)
    payload.update(metadata)
    return payload


def _drop_noise_fields(_: Any, __: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    event_dict.pop("color_message", None)
    event_dict.pop("task_name", None)
    return {key: value for key, value in event_dict.items() if value is not None}


def _build_shared_processors() -> list[Any]:
    processors: list[Any] = [
        _coerce_legacy_event_dict,
        structlog.contextvars.merge_contextvars,
        _add_service_metadata,
        _add_trace_metadata,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        _add_error_metadata,
        _sanitize_event_dict,
        structlog.processors.StackInfoRenderer(),
        _drop_noise_fields,
    ]
    return processors


def _build_formatter(*, renderer: Any, format_exceptions: bool) -> dict[str, Any]:
    processors: list[Any] = [structlog.stdlib.ProcessorFormatter.remove_processors_meta]
    if format_exceptions:
        processors.append(structlog.processors.format_exc_info)
    processors.append(renderer)
    return {
        "()": structlog.stdlib.ProcessorFormatter,
        "foreign_pre_chain": _build_shared_processors(),
        "processors": processors,
    }


def _build_handlers(*, console_formatter: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    handlers: dict[str, dict[str, Any]] = {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": settings.log_level.upper(),
            "formatter": console_formatter,
            "filters": ["max_info"],
            "stream": "ext://sys.stdout",
        },
        "stderr": {
            "class": "logging.StreamHandler",
            "level": "WARNING",
            "formatter": console_formatter,
            "stream": "ext://sys.stderr",
        },
    }
    root_handlers = ["stdout", "stderr"]

    if settings.log_to_file:
        log_file_path = Path(settings.log_file_path).expanduser()
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": settings.log_level.upper(),
            "formatter": "json",
            "filename": str(log_file_path),
            "maxBytes": settings.log_file_max_bytes,
            "backupCount": settings.log_file_backup_count,
            "encoding": "utf-8",
            "delay": True,
        }
        root_handlers.append("file")

    return handlers, root_handlers


def configure_logging(force: bool = False) -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED and not force:
        return

    resolved_log_format = _resolve_log_format()
    shared_processors = _build_shared_processors()
    console_renderer: Any
    if resolved_log_format == "json":
        console_renderer = structlog.processors.JSONRenderer(serializer=json.dumps, sort_keys=False)
    else:
        console_renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty() or sys.stderr.isatty())
    json_renderer = structlog.processors.JSONRenderer(serializer=json.dumps, sort_keys=False)
    console_formatter = "json" if resolved_log_format == "json" else "pretty"
    handlers, root_handlers = _build_handlers(console_formatter=console_formatter)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "max_info": {
                    "()": MaxLevelFilter,
                    "max_level": "INFO",
                }
            },
            "formatters": {
                "pretty": _build_formatter(renderer=console_renderer, format_exceptions=False),
                "json": _build_formatter(renderer=json_renderer, format_exceptions=True),
            },
            "handlers": handlers,
            "root": {
                "handlers": root_handlers,
                "level": settings.log_level.upper(),
            },
            "loggers": {
                "uvicorn.error": {"handlers": [], "level": settings.log_level.upper(), "propagate": True},
                "uvicorn.access": {"handlers": [], "level": "WARNING", "propagate": False},
                "celery": {"handlers": [], "level": settings.log_level.upper(), "propagate": True},
                "celery.app.trace": {"handlers": [], "level": settings.log_level.upper(), "propagate": True},
                "celery.redirected": {"handlers": [], "level": settings.log_level.upper(), "propagate": True},
                "celery.task": {"handlers": [], "level": settings.log_level.upper(), "propagate": True},
            },
        }
    )

    logging.captureWarnings(True)
    _LOGGING_CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.stdlib.get_logger(name)


def log_event(
    logger: structlog.stdlib.BoundLogger,
    event: str,
    *,
    level: str = "info",
    **fields: Any,
) -> None:
    getattr(logger, level)(event, extra=normalize_log_fields(fields))


def log_exception(
    logger: structlog.stdlib.BoundLogger,
    event: str,
    exc: BaseException,
    *,
    level: str = "error",
    **fields: Any,
) -> None:
    safe_fields = normalize_log_fields(fields)
    safe_fields.setdefault("error_type", exc.__class__.__name__)
    safe_fields.setdefault("error_message", str(exc))
    getattr(logger, level)(
        event,
        **safe_fields,
        exc_info=(type(exc), exc, exc.__traceback__),
    )


def duration_ms(started_at: float, finished_at: float) -> float:
    return round((finished_at - started_at) * 1000, 3)


def summarize_storage_reference(bucket_name: str | None, storage_key: str | None) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    if bucket_name:
        fields["storage_bucket"] = bucket_name
    if storage_key:
        fields["storage_key"] = summarize_storage_key(storage_key)
    return fields


def sha256_prefix(value: str | None, *, length: int = 12) -> str | None:
    if not value:
        return None
    return value[:length]
