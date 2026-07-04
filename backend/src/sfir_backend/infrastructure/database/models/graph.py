import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base
from sfir_backend.infrastructure.database.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class DependencyEdge(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dependency_edges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_component_id",
            "target_component_id",
            "edge_type",
            "source_key",
            "target_key",
            name="uq_dependency_edge_identity",
        ),
        Index("ix_dependency_edges_source", "organization_id", "source_component_id", "edge_type"),
        Index("ix_dependency_edges_target", "organization_id", "target_component_id", "edge_type"),
        Index("ix_dependency_edges_keys", "organization_id", "source_key", "target_key"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    source_component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE")
    )
    target_component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE")
    )
    edge_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_key: Mapped[str] = mapped_column(String(768), nullable=False)
    target_key: Mapped[str] = mapped_column(String(768), nullable=False)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    source_api: Mapped[str | None] = mapped_column(String(40))
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DependencySnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dependency_snapshots"
    __table_args__ = (Index("ix_dependency_snapshots_org_component", "organization_id", "root_key"),)

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    root_component_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_components.id", ondelete="CASCADE")
    )
    root_key: Mapped[str] = mapped_column(String(768), nullable=False)
    traversal_direction: Mapped[str] = mapped_column(String(40), nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    graph_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

