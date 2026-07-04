import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class MetadataSyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metadata_sync_runs"
    __table_args__ = (Index("ix_metadata_sync_runs_org_status", "organization_id", "status"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued")
    sync_type: Mapped[str] = mapped_column(String(40), nullable=False, default="full")
    api_version: Mapped[str] = mapped_column(String(12), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class MetadataComponent(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metadata_components"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "component_type",
            "full_name",
            "namespace_prefix",
            name="uq_metadata_component_identity",
        ),
        Index("ix_metadata_components_org_type", "organization_id", "component_type"),
        Index("ix_metadata_components_org_api_name", "organization_id", "api_name"),
        Index("ix_metadata_components_parent", "parent_component_id"),
        Index("ix_metadata_components_salesforce_id", "organization_id", "salesforce_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    parent_component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE")
    )
    component_type: Mapped[str] = mapped_column(String(80), nullable=False)
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    label: Mapped[str | None] = mapped_column(String(512))
    namespace_prefix: Mapped[str] = mapped_column(String(80), nullable=False, default="", server_default="")
    salesforce_id: Mapped[str | None] = mapped_column(String(18))
    durable_id: Mapped[str | None] = mapped_column(String(255))
    checksum: Mapped[str | None] = mapped_column(String(128))
    api_version: Mapped[str | None] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fields = relationship("MetadataField", back_populates="component", cascade="all, delete-orphan")


class MetadataField(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metadata_fields"
    __table_args__ = (
        UniqueConstraint("component_id", "api_name", name="uq_metadata_field_component_api_name"),
        Index("ix_metadata_fields_org_component", "organization_id", "component_id"),
        Index("ix_metadata_fields_org_api_name", "organization_id", "api_name"),
        Index("ix_metadata_fields_data_type", "organization_id", "data_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE"), nullable=False
    )
    api_name: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str | None] = mapped_column(String(512))
    data_type: Mapped[str] = mapped_column(String(80), nullable=False)
    relationship_name: Mapped[str | None] = mapped_column(String(255))
    reference_to: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    is_custom: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_formula: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_unique: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_external_id: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    formula: Mapped[str | None] = mapped_column(Text)
    inline_help_text: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    component = relationship("MetadataComponent", back_populates="fields")


class MetadataVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metadata_versions"
    __table_args__ = (Index("ix_metadata_versions_component_version", "component_id", "version_label"),)

    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_sync_runs.id", ondelete="SET NULL")
    )
    version_label: Mapped[str] = mapped_column(String(120), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class MetadataRawPayload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metadata_raw_payloads"
    __table_args__ = (Index("ix_metadata_raw_payloads_component_source", "component_id", "source_api"),)

    component_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE"), nullable=False
    )
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_sync_runs.id", ondelete="SET NULL")
    )
    source_api: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

