import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class DomainEvent:
    event_id: uuid.UUID
    occurred_at: datetime

    def __init__(self) -> None:
        self.event_id = uuid.uuid4()
        self.occurred_at = datetime.now(UTC)


@dataclass
class UserRegisteredEvent(DomainEvent):
    user_id: uuid.UUID
    email: str


@dataclass
class UserLoggedInEvent(DomainEvent):
    user_id: uuid.UUID
    organization_id: uuid.UUID | None


@dataclass
class UserLoggedOutEvent(DomainEvent):
    user_id: uuid.UUID
    session_id: uuid.UUID


@dataclass
class OrganizationCreatedEvent(DomainEvent):
    organization_id: uuid.UUID
    owner_id: uuid.UUID


@dataclass
class OrgMemberAddedEvent(DomainEvent):
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role_id: uuid.UUID
