import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sfir_backend.domain.value_objects.salesforce import (
    SalesforceConnectionStatus,
    SalesforceEnvironment,
)


@dataclass
class SalesforceConnection:
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    environment: SalesforceEnvironment
    instance_url: str
    org_id: str
    username: str
    api_version: str = "62.0"
    status: SalesforceConnectionStatus = SalesforceConnectionStatus.PENDING
    access_token_encrypted: str = ""
    refresh_token_encrypted: str = ""
    token_expires_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    last_failed_sync_at: datetime | None = None
    error_message: str = ""
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        environment: SalesforceEnvironment,
        instance_url: str,
        org_id: str,
        username: str,
        api_version: str = "62.0",
    ) -> "SalesforceConnection":
        return SalesforceConnection(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            environment=environment,
            instance_url=instance_url,
            org_id=org_id,
            username=username,
            api_version=api_version,
        )

    def mark_connected(
        self,
        access_token_encrypted: str,
        refresh_token_encrypted: str,
        expires_in: int = 3600,
    ) -> None:
        self.status = SalesforceConnectionStatus.CONNECTED
        self.is_active = True
        self.access_token_encrypted = access_token_encrypted
        self.refresh_token_encrypted = refresh_token_encrypted
        self.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(expires_in, 60),
        )
        self.error_message = ""
        self.updated_at = datetime.now(UTC)

    def mark_failed(self, error_message: str) -> None:
        self.status = SalesforceConnectionStatus.FAILED
        self.error_message = error_message
        self.last_failed_sync_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)

    def mark_disconnected(self) -> None:
        self.status = SalesforceConnectionStatus.DISCONNECTED
        self.is_active = False
        self.access_token_encrypted = ""
        self.refresh_token_encrypted = ""
        self.updated_at = datetime.now(UTC)

    def update_tokens(
        self,
        access_token_encrypted: str,
        refresh_token_encrypted: str | None = None,
        expires_in: int = 3600,
    ) -> None:
        self.access_token_encrypted = access_token_encrypted
        if refresh_token_encrypted:
            self.refresh_token_encrypted = refresh_token_encrypted
        self.token_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(expires_in, 60),
        )
        self.updated_at = datetime.now(UTC)
