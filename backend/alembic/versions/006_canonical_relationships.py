"""Canonical relationship store — typed, directional relationship rows.

Adds the canonical_relationships table: one row per directed edge between
canonical metadata documents (source identity -> target identity), typed by
relationship kind, keyed by (organization_id, source_identity,
target_identity, relationship_type) so repeated resolution runs are
idempotent. Rows carry a version (bumped when a deleted relationship
re-appears) and are soft-deleted, never physically removed.

Revision ID: 006
Revises: 005
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_relationships",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_identity", sa.String(64), nullable=False),
        sa.Column("source_api_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("source_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("target_identity", sa.String(64), nullable=False),
        sa.Column("target_api_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("target_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("relationship_type", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("previous_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_job_id", UUID(), nullable=True),
        sa.UniqueConstraint(
            "organization_id",
            "source_identity",
            "target_identity",
            "relationship_type",
            name="uq_canonical_relationships_src_tgt_type",
        ),
    )
    op.create_index(
        "ix_canonical_relationships_organization_id",
        "canonical_relationships",
        ["organization_id"],
    )
    op.create_index(
        "ix_canonical_relationships_source_identity",
        "canonical_relationships",
        ["source_identity"],
    )
    op.create_index(
        "ix_canonical_relationships_target_identity",
        "canonical_relationships",
        ["target_identity"],
    )


def downgrade() -> None:
    op.drop_table("canonical_relationships")
