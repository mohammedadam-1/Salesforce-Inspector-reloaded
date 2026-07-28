import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Permission:
    id: uuid.UUID
    role_id: uuid.UUID
    permission_slug: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
