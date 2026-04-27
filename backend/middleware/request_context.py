from __future__ import annotations

import time
import uuid
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.requests import Request

from backend.core.log_context import (
    bind_log_context,
    clear_log_context,
    consume_request_failure,
    get_correlation_id,
    set_correlation_id,
)
from backend.core.logging import duration_ms, get_logger, log_event, log_exception
from backend.core.metrics import metrics

logger = get_logger(__name__)


class RequestContextMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        clear_log_context()

        request = Request(scope)
        correlation = (
            get_correlation_id()
            or request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or uuid.uuid4().hex
        )
        set_correlation_id(correlation)
        bind_log_context(correlation_id=correlation, request_id=correlation)

        started_at = time.perf_counter()
        status_code = 500
        failure_logged = False

        log_event(
            logger,
            "request_started",
            method=request.method,
            path=request.url.path,
            status="started",
        )

        async def send_wrapper(message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = correlation
                headers["X-Correlation-ID"] = correlation
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            failure_logged = True
            finished_at = time.perf_counter()
            log_exception(
                logger,
                "request_failed",
                exc,
                method=request.method,
                path=request.url.path,
                status="failed",
                status_code=500,
                duration_ms=duration_ms(started_at, finished_at),
            )
            raise
        finally:
            finished_at = time.perf_counter()
            request_duration_ms = duration_ms(started_at, finished_at)
            metrics.increment(
                "http_requests_total",
                labels={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": str(status_code),
                },
            )
            metrics.observe(
                "http_request_duration_seconds",
                request_duration_ms / 1000,
                labels={"method": request.method, "path": request.url.path},
            )

            if not failure_logged:
                failure_context = consume_request_failure(scope)
                if failure_context is not None:
                    failure_context = dict(failure_context)
                    for key in ("status", "status_code", "duration_ms", "method", "path"):
                        failure_context.pop(key, None)

                if failure_context is not None or status_code >= 500:
                    log_event(
                        logger,
                        "request_failed",
                        level="error" if status_code >= 500 else "warning",
                        method=request.method,
                        path=request.url.path,
                        status="failed",
                        status_code=status_code,
                        duration_ms=request_duration_ms,
                        **(failure_context or {}),
                    )
                else:
                    log_event(
                        logger,
                        "request_finished",
                        method=request.method,
                        path=request.url.path,
                        status="succeeded",
                        status_code=status_code,
                        duration_ms=request_duration_ms,
                    )

            clear_log_context()
