import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sfir_backend.domain.value_objects.email import Email
from sfir_backend.domain.value_objects.user_status import UserStatus


@dataclass
class User:
    id: uuid.UUID
    email: Email
    password_hash: str
    display_name: str
    status: UserStatus = UserStatus.ACTIVE
    is_locked: bool = False
    locked_until: datetime | None = None
    login_attempts: int = 0
    last_login_at: datetime | None = None
    email_verified_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def create(
        email: str,
        password_hash: str,
        display_name: str,
    ) -> "User":
        return User(
            id=uuid.uuid4(),
            email=Email(email),
            password_hash=password_hash,
            display_name=display_name,
        )

    def record_login(self) -> None:
        self.last_login_at = datetime.now(UTC)
        self.login_attempts = 0
        self.updated_at = datetime.now(UTC)

    def record_failed_login(self) -> None:
        self.login_attempts += 1
        self.updated_at = datetime.now(UTC)

    def lock(self, duration_minutes: int = 15) -> None:
        self.is_locked = True
        self.locked_until = datetime.now(UTC).replace(
            second=0, microsecond=0,
        )
        self.updated_at = datetime.now(UTC)
        _ = duration_minutes

    def unlock(self) -> None:
        self.is_locked = False
        self.locked_until = None
        self.login_attempts = 0
        self.updated_at = datetime.now(UTC)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE and not self.is_locked

    @property
    def can_login(self) -> bool:
        if not self.is_active:
            return False
        if self.is_locked and self.locked_until:
            return datetime.now(UTC) > self.locked_until
        return True
