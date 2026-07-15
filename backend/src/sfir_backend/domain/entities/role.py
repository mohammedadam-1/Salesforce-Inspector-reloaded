import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass
class Role:
    id: uuid.UUID
    name: str
    slug: str
    description: str = ""
    is_system: bool = False
    organization_id: uuid.UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create_system(
        name: str,
        slug: str,
        description: str = "",
    ) -> "Role":
        return Role(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description=description,
            is_system=True,
        )

    @staticmethod
    def create_custom(
        name: str,
        slug: str,
        organization_id: uuid.UUID,
        description: str = "",
    ) -> "Role":
        return Role(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description=description,
            is_system=False,
            organization_id=organization_id,
        )
