"""Organization request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OrganizationCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: str = Field(..., min_length=1, max_length=160, pattern=r"^[a-z0-9-]+$")
    salesforce_org_id: str | None = Field(default=None, max_length=18)
    instance_url: str | None = Field(default=None, max_length=512)
    environment: str = Field(default="unknown", max_length=40)
    settings: dict[str, Any] | None = None


class OrganizationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    instance_url: str | None = Field(default=None, max_length=512)
    environment: str | None = Field(default=None, max_length=40)
    status: str | None = Field(default=None, max_length=40)
    settings: dict[str, Any] | None = None


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    salesforce_org_id: str | None
    instance_url: str | None
    environment: str
    status: str
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrganizationMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: str
    status: str
    accepted_at: datetime | None

    model_config = {"from_attributes": True}
