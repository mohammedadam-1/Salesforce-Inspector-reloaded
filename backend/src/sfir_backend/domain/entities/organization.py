import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.value_objects.user_status import OrganizationStatus


@dataclass
class Organization:
    id: uuid.UUID
    name: str
    slug: str
    owner_id: uuid.UUID
    description: str = ""
    status: OrganizationStatus = OrganizationStatus.ACTIVE
    settings: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        name: str,
        slug: str,
        owner_id: uuid.UUID,
        description: str = "",
    ) -> "Organization":
        return Organization(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            owner_id=owner_id,
            description=description,
        )
