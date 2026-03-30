from __future__ import annotations

import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from backend.core.logging import get_logger, request_id_context
from backend.core.metrics import metrics

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        token = request_id_context.set(request_id)
        start = time.perf_counter()
        response = None

        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start
            status_code = getattr(response, "status_code", 500)
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
                duration,
                labels={
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            logger.info(
                "HTTP request completed.",
                extra={
                    "event": "http_request_completed",
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": round(duration * 1000, 3),
                    },
                },
            )
            if response is not None:
                response.headers["x-request-id"] = request_id
            request_id_context.reset(token)
