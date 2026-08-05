import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sfir_backend.domain.value_objects.salesforce import (
    SalesforceEnvironment,
)
from sfir_backend.shared.exceptions.application import InvalidOAuthStateError


@dataclass
class OAuthSession:
    """Server-side OAuth authorization session (state-bound).

    The ``state`` parameter is the only credential the callback receives;
    it is bound server-side to the SFIR user and org that initiated the
    flow, along with the PKCE code verifier which must never leave the
    server. ``consumed_at`` marks single-use redemption.
    """

    id: uuid.UUID
    state: str
    code_verifier: str
    user_id: uuid.UUID
    organization_id: uuid.UUID
    environment: SalesforceEnvironment
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    @staticmethod
    def create(
        *,
        state: str,
        code_verifier: str,
        user_id: uuid.UUID,
        organization_id: uuid.UUID,
        environment: SalesforceEnvironment,
        ttl_seconds: int = 600,
    ) -> "OAuthSession":
        now = datetime.now(UTC)
        return OAuthSession(
            id=uuid.uuid4(),
            state=state,
            code_verifier=code_verifier,
            user_id=user_id,
            organization_id=organization_id,
            environment=environment,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )

    @property
    def is_consumed(self) -> bool:
        return self.consumed_at is not None

    def is_expired(self, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    def consume(self) -> None:
        if self.consumed_at is None:
            self.consumed_at = datetime.now(UTC)

    def validate(
        self,
        environment: SalesforceEnvironment,
        now: datetime | None = None,
    ) -> None:
        """Centralized callback validation: environment, expiry, replay."""
        if self.environment != environment:
            raise InvalidOAuthStateError("OAuth state environment mismatch")
        if self.is_expired(now):
            raise InvalidOAuthStateError("OAuth state expired")
        if self.is_consumed:
            raise InvalidOAuthStateError("OAuth state already used")
