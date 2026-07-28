import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SalesforceConnectRequest:
    environment: str = "production"


@dataclass
class SalesforceConnectResponse:
    authorization_url: str
    state: str
    code_verifier: str
    environment: str


@dataclass
class SalesforceCallbackRequest:
    code: str
    state: str
    code_verifier: str
    environment: str


@dataclass
class SalesforceConnectionResponse:
    id: uuid.UUID
    organization_id: uuid.UUID
    environment: str
    instance_url: str
    org_id: str
    username: str
    api_version: str
    status: str
    is_active: bool
    last_successful_sync_at: datetime | None = None
    last_failed_sync_at: datetime | None = None
    error_message: str = ""
    created_at: datetime | None = None


@dataclass
class SalesforceHealthResponse:
    connection_id: uuid.UUID
    status: str
    is_token_valid: bool
    limits: dict | None = None
    org_info: dict | None = None
    error_message: str = ""
