"""Search index storage.

One row per searchable graph node identity per tenant, keyed by
(organization_id, identity). Rows are versioned, idempotently upserted,
only ever soft-deleted, and carry the relationship context used for
metadata lookup and ranking.

Note: distinct from the legacy ``SearchDocumentModel`` (metadata_components)
which persists full-text documents for the legacy in-memory search engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from sfir_backend.infrastructure.database.base import Base


class SearchIndexDocumentModel(Base):
    __tablename__ = "search_index_documents"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "identity", name="uq_search_index_documents_org_identity",
        ),
        Index(
            "ix_search_index_documents_lower_api_name",
            "organization_id",
            text("lower(api_name)"),
        ),
        Index(
            "ix_search_index_documents_lower_developer_name",
            "organization_id",
            text("lower(developer_name)"),
        ),
        Index(
            "ix_search_index_documents_lower_display_name",
            "organization_id",
            text("lower(display_name)"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID, primary_key=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    identity: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    developer_name: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False, default="", index=True)
    namespace: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    content: Mapped[str] = mapped_column(String(4096), nullable=False, default="")
    object_api_name: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    parent_identities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    child_identities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reference_identities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    relationship_types: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    reference_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    relationship_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
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
