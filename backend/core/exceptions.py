from __future__ import annotations


class AppError(Exception):
    status_code = 400
    code = "app_error"

    def __init__(self, message: str, *, code: str | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code
        self.message = message


class ValidationAppError(AppError):
    status_code = 400
    code = "validation_error"


class UnsupportedModalityAppError(ValidationAppError):
    code = "unsupported_modality"


class NotFoundAppError(AppError):
    status_code = 404
    code = "not_found"


class ConflictAppError(AppError):
    status_code = 409
    code = "conflict"


class UnauthorizedAppError(AppError):
    status_code = 401
    code = "unauthorized"


class ConfigurationAppError(AppError):
    status_code = 503
    code = "configuration_error"


class DependencyAppError(AppError):
    status_code = 503
    code = "dependency_error"


class RetryableTaskError(AppError):
    status_code = 503
    code = "retryable_task_error"
