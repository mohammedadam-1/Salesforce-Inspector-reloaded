"""Salesforce connection schemas."""

from datetime import datetime

from pydantic import BaseModel


class ConnectionResponse(BaseModel):
    id: str
    organization_id: str
    connection_type: str
    salesforce_org_id: str
    instance_url: str
    api_version: str
    status: str
    token_expires_at: datetime | None
    last_refreshed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
