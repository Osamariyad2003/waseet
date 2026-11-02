"""Typed errors mapped onto HTTP responses.

The domain raises its own exceptions (`app/domain/errors.py`); this module is
the only place that knows what status code each one deserves. Responses
carry a stable machine-readable `code` and a safe message — never a stack
trace, never a vendor payload.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.errors import (
    AIError,
    ConflictError,
    CriteriaNotConfirmed,
    DealNotFound,
    DomainError,
    InvalidTransition,
    NotAuthorizedForDeal,
    PayPalError,
    SettlementError,
    TransitionGuardFailed,
    WebhookVerificationFailed,
)

logger = structlog.get_logger(__name__)

STATUS_BY_ERROR: dict[type[DomainError], int] = {
    DealNotFound: status.HTTP_404_NOT_FOUND,
    NotAuthorizedForDeal: status.HTTP_403_FORBIDDEN,
    # A transition that is not allowed from the current state is a conflict
    # with the deal's reality, not a malformed request.
    InvalidTransition: status.HTTP_409_CONFLICT,
    TransitionGuardFailed: status.HTTP_409_CONFLICT,
    CriteriaNotConfirmed: status.HTTP_409_CONFLICT,
    ConflictError: status.HTTP_409_CONFLICT,
    SettlementError: status.HTTP_502_BAD_GATEWAY,
    PayPalError: status.HTTP_502_BAD_GATEWAY,
    AIError: status.HTTP_503_SERVICE_UNAVAILABLE,
    WebhookVerificationFailed: status.HTTP_401_UNAUTHORIZED,
}


class AuthenticationError(DomainError):
    """Bad credentials, or a missing/invalid bearer token."""

    code = "authentication_failed"


class ValidationError(DomainError):
    """A request that is well-formed but semantically invalid."""

    code = "validation_error"


STATUS_BY_ERROR[AuthenticationError] = status.HTTP_401_UNAUTHORIZED
STATUS_BY_ERROR[ValidationError] = status.HTTP_422_UNPROCESSABLE_CONTENT


def error_body(code: str, message: str, **extra: object) -> dict[str, object]:
    return {"error": {"code": code, "message": message, **extra}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        status_code = STATUS_BY_ERROR.get(type(exc), status.HTTP_400_BAD_REQUEST)
        logger.info(
            "request.domain_error",
            code=exc.code,
            status_code=status_code,
            path=request.url.path,
        )
        headers = (
            {"WWW-Authenticate": "Bearer"} if status_code == status.HTTP_401_UNAUTHORIZED else None
        )
        return JSONResponse(
            status_code=status_code,
            content=error_body(exc.code, exc.message),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        """Pydantic's own report, flattened and stripped of input echoes."""
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or "body",
                "message": error["msg"],
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body("validation_error", "the request is invalid", fields=fields),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Nothing internal reaches the client: the detail goes to the log."""
        logger.exception(
            "request.unhandled_error",
            error_type=type(exc).__name__,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body("internal_error", "an unexpected error occurred"),
        )
