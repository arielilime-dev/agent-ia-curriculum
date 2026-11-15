"""Domain exceptions mapped to RFC 7807-friendly JSON error responses.

The API returns a stable machine-readable ``code`` next to the human-readable
``detail`` so that clients can branch on errors without parsing prose.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for expected application errors."""

    status_code: int = 500
    code: str = "internal_error"
    default_message: str = "Internal server error"

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.status_code = status_code or self.status_code
        self.code = code or self.code
        self.details = details
        self.headers = headers or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"detail": self.message, "code": self.code}
        if self.details:
            payload["details"] = self.details
        return payload


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    default_message = "Resource not found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    default_message = "Resource already exists"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"
    default_message = "Not authenticated"

    def __init__(self, message: str | None = None, **kwargs: Any) -> None:
        headers = kwargs.pop("headers", None) or {"WWW-Authenticate": "Bearer"}
        super().__init__(message, headers=headers, **kwargs)


class ForbiddenError(AppError):
    status_code = 403
    code = "forbidden"
    default_message = "Operation not allowed"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"
    default_message = "Invalid input"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"
    default_message = "Uploaded file is too large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"
    default_message = "Unsupported file type"


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"
    default_message = "Too many requests"

    def __init__(self, retry_after: int = 60, **kwargs: Any) -> None:
        super().__init__(
            f"Too many requests. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
            details={"retry_after": retry_after},
            **kwargs,
        )


class ExternalServiceError(AppError):
    status_code = 502
    code = "external_service_error"
    default_message = "Upstream service failed"
