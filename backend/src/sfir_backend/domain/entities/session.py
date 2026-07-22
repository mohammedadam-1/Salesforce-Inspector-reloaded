import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Session:
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    refresh_token_id: uuid.UUID | None = None
    ip_address: str = ""
    user_agent: str = ""
    is_active: bool = True
    expires_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        user_id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
        ip_address: str = "",
        user_agent: str = "",
        expires_at: datetime | None = None,
    ) -> "Session":
        return Session(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=organization_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
