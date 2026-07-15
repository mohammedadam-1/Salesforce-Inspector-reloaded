from typing import Any


class BaseAppException(Exception):
    """Base exception for all application exceptions.

    Attributes:
        status_code: HTTP status code equivalent.
        code: Machine-readable error code.
        detail: Human-readable message.
        context: Additional metadata (logged, not exposed to clients).
    """

    def __init__(
        self,
        status_code: int = 500,
        code: str = "INTERNAL_ERROR",
        detail: str = "An unexpected error occurred.",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.context = context or {}
        super().__init__(self.detail)


class DomainException(BaseAppException):
    """Base for domain layer exceptions."""

    def __init__(
        self,
        code: str = "DOMAIN_ERROR",
        detail: str = "Domain rule violation.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=400,
            code=code,
            detail=detail,
            context=context,
        )


class ApplicationException(BaseAppException):
    """Base for application layer exceptions."""

    def __init__(
        self,
        status_code: int = 400,
        code: str = "APPLICATION_ERROR",
        detail: str = "Application error.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            code=code,
            detail=detail,
            context=context,
        )


class InfrastructureException(BaseAppException):
    """Base for infrastructure layer exceptions."""

    def __init__(
        self,
        status_code: int = 500,
        code: str = "INFRASTRUCTURE_ERROR",
        detail: str = "Infrastructure error.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            code=code,
            detail=detail,
            context=context,
        )
