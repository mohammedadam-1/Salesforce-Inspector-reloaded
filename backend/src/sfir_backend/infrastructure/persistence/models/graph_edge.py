"""Dependency graph edge storage.

One row per directed, typed edge per tenant, keyed by
(organization_id, source identity, target identity, relationship type).
Edges mirror canonical relationships: versioned, idempotently upserted,
only ever soft-deleted.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base


class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_identity",
            "target_identity",
            "relationship_type",
            name="uq_graph_edges_src_tgt_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_api_name: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target_identity: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    target_api_name: Mapped[str] = mapped_column(String(512), nullable=False)
    target_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_sync_job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID, nullable=True, default=None,
    )
