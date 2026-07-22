import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CreateOrganizationRequest:
    name: str
    slug: str
    description: str = ""


@dataclass
class OrganizationResponse:
    id: uuid.UUID
    name: str
    slug: str
    description: str
    status: str
    owner_id: uuid.UUID
    member_count: int = 0
    created_at: datetime | None = None


@dataclass
class SwitchOrganizationResponse:
    organization_id: uuid.UUID
    organization_name: str
    role_slug: str
    access_token: str
    expires_in: int
