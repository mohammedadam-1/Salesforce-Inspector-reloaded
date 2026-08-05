from typing import Any

from sfir_backend.shared.exceptions.base import InfrastructureException


class DatabaseError(InfrastructureException):
    """Raised when a database operation fails."""

    def __init__(
        self,
        message: str = "Database operation failed.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=500,
            code="DATABASE_ERROR",
            detail=message,
            context=context,
        )


class CacheError(InfrastructureException):
    """Raised when a cache operation fails."""

    def __init__(
        self,
        message: str = "Cache operation failed.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=500,
            code="CACHE_ERROR",
            detail=message,
            context=context,
        )


class SalesforceApiError(InfrastructureException):
    """Raised when Salesforce API returns an error."""

    def __init__(
        self,
        message: str = "Salesforce API error.",
        status_code: int = 502,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=status_code,
            code="SALESFORCE_API_ERROR",
            detail=message,
            context=context,
        )


class LlmProviderError(InfrastructureException):
    """Raised when an LLM provider returns an error."""

    def __init__(
        self,
        message: str = "LLM provider error.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=502,
            code="LLM_PROVIDER_ERROR",
            detail=message,
            context=context,
        )


class SyncCancelledError(InfrastructureException):
    """Raised by the sync worker when a running sync job is cancelled.

    Used to abort long-running metadata downloads cooperatively so the
    job is not marked COMPLETED after a cancellation was requested.
    """

    def __init__(
        self,
        message: str = "Sync job was cancelled.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            status_code=409,
            code="SYNC_CANCELLED",
            detail=message,
            context=context,
        )
