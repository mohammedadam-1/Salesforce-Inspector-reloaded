"""Tests for the exception framework."""

from sfir_backend.shared.exceptions.application import (
    AuthorizationFailedError,
    RateLimitExceededError,
)
from sfir_backend.shared.exceptions.base import (
    ApplicationException,
    BaseAppException,
    DomainException,
    InfrastructureException,
)
from sfir_backend.shared.exceptions.domain import (
    EntityNotFoundError,
)
from sfir_backend.shared.exceptions.infrastructure import (
    CacheError,
    DatabaseError,
    SalesforceApiError,
)


class TestExceptions:
    """Verify exception hierarchy and behavior."""

    def test_base_exception_defaults(self) -> None:
        exc = BaseAppException()
        assert exc.status_code == 500
        assert exc.code == "INTERNAL_ERROR"
        assert exc.detail == "An unexpected error occurred."

    def test_domain_exception(self) -> None:
        exc = DomainException(code="TEST", detail="Test error")
        assert exc.status_code == 400

    def test_application_exception(self) -> None:
        exc = ApplicationException(status_code=403)
        assert exc.status_code == 403

    def test_infrastructure_exception(self) -> None:
        exc = InfrastructureException(status_code=502)
        assert exc.status_code == 502

    def test_entity_not_found(self) -> None:
        exc = EntityNotFoundError(
            entity_type="User",
            entity_id="abc-123",
        )
        assert exc.code == "ENTITY_NOT_FOUND"
        assert "User" in exc.detail
        assert "abc-123" in exc.detail

    def test_rate_limit_exceeded(self) -> None:
        exc = RateLimitExceededError(retry_after=30)
        assert exc.status_code == 429
        assert exc.context.get("retry_after") == 30

    def test_authorization_failed(self) -> None:
        exc = AuthorizationFailedError()
        assert exc.status_code == 403
        assert exc.code == "AUTHORIZATION_FAILED"

    def test_infrastructure_errors(self) -> None:
        db_err = DatabaseError()
        assert db_err.code == "DATABASE_ERROR"

        cache_err = CacheError()
        assert cache_err.code == "CACHE_ERROR"

        sf_err = SalesforceApiError()
        assert sf_err.code == "SALESFORCE_API_ERROR"

    def test_exception_string_representation(self) -> None:
        exc = DomainException(detail="Something went wrong")
        assert str(exc) == "Something went wrong"
