import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfir_backend.infrastructure.database.base import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(320), unique=True, nullable=False, index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", index=True,
    )
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )

    sessions = relationship("SessionModel", back_populates="user", lazy="selectin")
    refresh_tokens = relationship("RefreshTokenModel", back_populates="user", lazy="selectin")
    memberships = relationship("OrgMemberModel", back_populates="user", lazy="selectin")
