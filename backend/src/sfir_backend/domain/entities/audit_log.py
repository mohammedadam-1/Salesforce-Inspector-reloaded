import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class AuditLogEntry:
    id: uuid.UUID
    user_id: uuid.UUID | None
    organization_id: uuid.UUID | None
    action: str
    resource_type: str
    resource_id: str
    details: dict | None = None
    ip_address: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: uuid.UUID | None = None,
        organization_id: uuid.UUID | None = None,
        details: dict | None = None,
        ip_address: str = "",
    ) -> "AuditLogEntry":
        return AuditLogEntry(
            id=uuid.uuid4(),
            user_id=user_id,
            organization_id=organization_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
