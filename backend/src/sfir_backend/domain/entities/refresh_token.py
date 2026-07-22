import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class RefreshToken:
    id: uuid.UUID
    user_id: uuid.UUID
    token_hash: str
    expires_at: datetime
    is_revoked: bool = False
    revoked_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_expired(self) -> bool:
        return datetime.now(UTC) > self.expires_at

    def revoke(self) -> None:
        self.is_revoked = True
        self.revoked_at = datetime.now(UTC)
