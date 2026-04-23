from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.core.exceptions import AppError
from backend.core.log_context import get_correlation_id, mark_request_failure


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        mark_request_failure(
            request,
            status_code=exc.status_code,
            error_type=exc.__class__.__name__,
            error_message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": get_correlation_id(),
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        mark_request_failure(
            request,
            status_code=422,
            error_type=exc.__class__.__name__,
            error_message="Request validation failed.",
        )
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "request_validation_error",
                    "message": "Request validation failed.",
                    "details": exc.errors(),
                    "request_id": get_correlation_id(),
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_sqlalchemy_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        mark_request_failure(
            request,
            status_code=500,
            error_type=exc.__class__.__name__,
            error_message="A database error occurred.",
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "database_error",
                    "message": "A database error occurred.",
                    "request_id": get_correlation_id(),
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        mark_request_failure(
            request,
            status_code=500,
            error_type=exc.__class__.__name__,
            error_message="An unexpected error occurred.",
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected error occurred.",
                    "request_id": get_correlation_id(),
                    "correlation_id": get_correlation_id(),
                }
            },
        )
