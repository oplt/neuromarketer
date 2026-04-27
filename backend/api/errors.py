from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError, SQLAlchemyError

from backend.core.exceptions import AppError
from backend.core.log_context import get_correlation_id, mark_request_failure

logger = logging.getLogger(__name__)


def _error_response(
        *,
        status_code: int,
        code: str,
        message: str,
        details: Any | None = None,
) -> JSONResponse:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": get_correlation_id(),
        "correlation_id": get_correlation_id(),
    }

    if details is not None:
        error["details"] = details

    return JSONResponse(
        status_code=status_code,
        content={"error": error},
    )


def _mark_failure(
        request: Request,
        *,
        status_code: int,
        error_type: str,
        error_message: str,
) -> None:
    mark_request_failure(
        request,
        status_code=status_code,
        error_type=error_type,
        error_message=error_message,
    )


def _validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    safe_details: list[dict[str, Any]] = []

    for error in exc.errors():
        safe_details.append(
            {
                "loc": error.get("loc"),
                "msg": error.get("msg"),
                "type": error.get("type"),
            }
        )

    return safe_details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        _mark_failure(
            request,
            status_code=exc.status_code,
            error_type=exc.__class__.__name__,
            error_message=exc.message,
        )

        logger.warning(
            "Application error",
            extra={
                "status_code": exc.status_code,
                "error_code": exc.code,
                "error_type": exc.__class__.__name__,
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
            request: Request,
            exc: RequestValidationError,
    ) -> JSONResponse:
        _mark_failure(
            request,
            status_code=422,
            error_type=exc.__class__.__name__,
            error_message="Request validation failed.",
        )

        logger.info(
            "Request validation failed",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
                "errors": _validation_details(exc),
            },
        )

        return _error_response(
            status_code=422,
            code="request_validation_error",
            message="Request validation failed.",
            details=_validation_details(exc),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError) -> JSONResponse:
        _mark_failure(
            request,
            status_code=409,
            error_type=exc.__class__.__name__,
            error_message="Database integrity constraint failed.",
        )

        logger.exception(
            "Database integrity error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=409,
            code="database_integrity_error",
            message="The requested operation conflicts with existing data.",
        )

    @app.exception_handler(OperationalError)
    async def handle_operational_error(request: Request, exc: OperationalError) -> JSONResponse:
        _mark_failure(
            request,
            status_code=503,
            error_type=exc.__class__.__name__,
            error_message="Database is temporarily unavailable.",
        )

        logger.exception(
            "Database operational error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=503,
            code="database_unavailable",
            message="The service is temporarily unavailable. Please try again later.",
        )

    @app.exception_handler(ProgrammingError)
    async def handle_programming_error(request: Request, exc: ProgrammingError) -> JSONResponse:
        _mark_failure(
            request,
            status_code=500,
            error_type=exc.__class__.__name__,
            error_message="Database query/schema error.",
        )

        logger.exception(
            "Database programming error. Check migrations/schema/query compatibility.",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=500,
            code="database_query_error",
            message="A database error occurred.",
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        _mark_failure(
            request,
            status_code=500,
            error_type=exc.__class__.__name__,
            error_message="A database error occurred.",
        )

        logger.exception(
            "Unhandled SQLAlchemy error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=500,
            code="database_error",
            message="A database error occurred.",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        _mark_failure(
            request,
            status_code=500,
            error_type=exc.__class__.__name__,
            error_message="An unexpected error occurred.",
        )

        logger.exception(
            "Unhandled application error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "correlation_id": get_correlation_id(),
            },
        )

        return _error_response(
            status_code=500,
            code="internal_server_error",
            message="An unexpected error occurred.",
        )