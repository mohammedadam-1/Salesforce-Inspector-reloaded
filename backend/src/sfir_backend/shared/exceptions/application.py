from typing import Any

from sfir_backend.shared.exceptions.base import ApplicationException


class AuthorizationFailedError(ApplicationException):
    """Raised when user lacks permissions."""

    def __init__(
        self,
        message: str = "Insufficient permissions.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=403,
            code="AUTHORIZATION_FAILED",
            detail=message,
            context=context,
        )


class AuthenticationFailedError(ApplicationException):
    """Raised when authentication fails."""

    def __init__(
        self,
        message: str = "Authentication failed.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=401,
            code="AUTHENTICATION_FAILED",
            detail=message,
            context=context,
        )


class RateLimitExceededError(ApplicationException):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str = "Rate limit exceeded.",
        retry_after: int = 30,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=429,
            code="RATE_LIMIT_EXCEEDED",
            detail=message,
            context={"retry_after": retry_after, **(context or {})},
        )


class ConflictError(ApplicationException):
    """Raised when a resource conflict occurs."""

    def __init__(
        self,
        message: str = "Resource conflict.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=409,
            code="CONFLICT",
            detail=message,
            context=context,
        )
