import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        Index("ix_organizations_salesforce_org_id", "salesforce_org_id"),
        Index("ix_organizations_slug", "slug"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    salesforce_org_id: Mapped[str | None] = mapped_column(String(18), unique=True)
    instance_url: Mapped[str | None] = mapped_column(String(512))
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    memberships = relationship("OrganizationMembership", back_populates="organization")


class OrganizationMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_organization_membership"),
        Index("ix_org_memberships_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    invited_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    organization = relationship("Organization", back_populates="memberships")
    user = relationship("User", back_populates="memberships", foreign_keys=[user_id])

