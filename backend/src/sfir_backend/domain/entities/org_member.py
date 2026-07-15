import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.value_objects.user_status import OrgMemberStatus


@dataclass
class OrgMember:
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
    status: OrgMemberStatus = OrgMemberStatus.ACTIVE
    is_default: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        organization_id: uuid.UUID,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        is_default: bool = False,
    ) -> "OrgMember":
        return OrgMember(
            id=uuid.uuid4(),
            organization_id=organization_id,
            user_id=user_id,
            role_id=role_id,
            is_default=is_default,
        )
