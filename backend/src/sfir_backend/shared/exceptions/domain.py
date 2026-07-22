from typing import Any

from sfir_backend.shared.exceptions.base import DomainException


class EntityNotFoundError(DomainException):
    """Raised when a domain entity is not found."""

    def __init__(
        self,
        entity_type: str = "Entity",
        entity_id: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="ENTITY_NOT_FOUND",
            detail=f"{entity_type} not found: {entity_id}",
            context=context,
        )


class InvalidStateError(DomainException):
    """Raised when an operation is attempted in an invalid state."""

    def __init__(
        self,
        message: str = "Invalid state for operation.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="INVALID_STATE",
            detail=message,
            context=context,
        )


class ValidationError(DomainException):
    """Raised when domain validation fails."""

    def __init__(
        self,
        message: str = "Validation failed.",
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code="VALIDATION_ERROR",
            detail=message,
            context=context,
        )
