import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class SalesforceConnection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "salesforce_connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "connection_type", name="uq_salesforce_connection_type"),
        Index("ix_salesforce_connections_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    connection_type: Mapped[str] = mapped_column(String(40), nullable=False, default="oauth")
    salesforce_org_id: Mapped[str] = mapped_column(String(18), nullable=False)
    instance_url: Mapped[str] = mapped_column(String(512), nullable=False)
    login_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_version: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    scopes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SalesforceApiUsage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "salesforce_api_usage"
    __table_args__ = (
        Index("ix_salesforce_api_usage_org_window", "organization_id", "window_started_at"),
        Index("ix_salesforce_api_usage_endpoint", "organization_id", "api_family", "endpoint"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    api_family: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128))
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

