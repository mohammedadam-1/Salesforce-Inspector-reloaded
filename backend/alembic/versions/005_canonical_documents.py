"""Canonical metadata store — current-state canonical documents.

Adds the canonical_documents table: one row per stable metadata identity
per organization, holding the current version, previous version, content
fingerprint and lifecycle timestamps. This is the system of record for
normalized metadata; it is append-only in spirit — rows are soft-deleted,
never physically removed. Version history lives in metadata_versions.

- identity       stable id (hash of org, platform, type, api name, namespace)
- version        current version number
- previous_version  version number before the latest change (0 if none)
- fingerprint    content + relationship fingerprint of the current version
- status         active / deleted
- deleted        denormalized boolean flag for cheap queries
- first_seen_at / last_seen_at / deleted_at  lifecycle timestamps
- UNIQUE (organization_id, identity)  — upsert target, no duplicates

Revision ID: 005
Revises: 004
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "005"
down_revision: str = "004"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "canonical_documents",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("api_name", sa.String(512), nullable=False),
        sa.Column("developer_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("namespace", sa.String(256), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("previous_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("status", sa.String(24), nullable=False, server_default="active"),
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
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_job_id", UUID(), nullable=True),
        sa.Column("payload", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint(
            "organization_id",
            "identity",
            name="uq_canonical_documents_org_identity",
        ),
    )
    op.create_index(
        "ix_canonical_documents_organization_id",
        "canonical_documents",
        ["organization_id"],
    )
    op.create_index(
        "ix_canonical_documents_type",
        "canonical_documents",
        ["type"],
    )
    op.create_index(
        "ix_canonical_documents_status",
        "canonical_documents",
        ["status"],
    )


def downgrade() -> None:
    op.drop_table("canonical_documents")
