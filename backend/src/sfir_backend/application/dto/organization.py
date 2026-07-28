import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class CreateOrganizationRequest:
    name: str
    slug: str
    description: str = ""


@dataclass
class UpdateOrganizationRequest:
    name: str | None = None
    slug: str | None = None
    description: str | None = None


@dataclass
class OrganizationResponse:
    id: uuid.UUID
    name: str
    slug: str
    description: str
    status: str
    owner_id: uuid.UUID
    connection_status: str = ""
    org_id: str = ""
    api_version: str = ""
    connected_user: str = ""
    last_sync_at: str | None = None
    total_metadata: int = 0
    member_count: int = 0
    created_at: datetime | None = None


@dataclass
class SwitchOrganizationResponse:
    organization_id: uuid.UUID
    organization_name: str
    role_slug: str
    access_token: str
    expires_in: int
