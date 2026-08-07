"""Search index store — searchable documents derived from canonical data.

Adds the search_index_documents table: one searchable row per graph node
identity per tenant, keyed by (organization_id, identity), enriched with
relationship context (parent object, references, relationship kinds,
reference count, relationship score). Rows are versioned and soft-deleted,
never physically removed. Case-insensitive prefix lookups are served by
lower() expression indexes; fuzzy lookups fall back to substring
matching (no trigram extension required).

Revision ID: 008
Revises: 007
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "008"
down_revision: str = "007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "search_index_documents",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("metadata_type", sa.String(128), nullable=False),
        sa.Column("api_name", sa.String(512), nullable=False),
        sa.Column("developer_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("display_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("namespace", sa.String(256), nullable=True),
        sa.Column("content", sa.String(4096), nullable=False, server_default=""),
        sa.Column("object_api_name", sa.String(512), nullable=False, server_default=""),
        sa.Column(
            "parent_identities",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "child_identities",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "reference_identities",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "relationship_types",
            sa.dialects.postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("reference_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("relationship_score", sa.Integer(), nullable=False, server_default="0"),
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
            "identity",
            name="uq_search_index_documents_org_identity",
        ),
    )
    op.create_index(
        "ix_search_index_documents_organization_id",
        "search_index_documents",
        ["organization_id"],
    )
    op.create_index(
        "ix_search_index_documents_metadata_type",
        "search_index_documents",
        ["metadata_type"],
    )
    op.create_index(
        "ix_search_index_documents_api_name",
        "search_index_documents",
        ["api_name"],
    )
    op.create_index(
        "ix_search_index_documents_developer_name",
        "search_index_documents",
        ["developer_name"],
    )
    op.create_index(
        "ix_search_index_documents_display_name",
        "search_index_documents",
        ["display_name"],
    )
    op.create_index(
        "ix_search_index_documents_namespace",
        "search_index_documents",
        ["namespace"],
    )
    op.create_index(
        "ix_search_index_documents_reference_count",
        "search_index_documents",
        ["reference_count"],
    )
    op.create_index(
        "ix_search_index_documents_relationship_score",
        "search_index_documents",
        ["relationship_score"],
    )
    op.execute(
        "CREATE INDEX ix_search_index_documents_lower_api_name "
        "ON search_index_documents (organization_id, lower(api_name))",
    )
    op.execute(
        "CREATE INDEX ix_search_index_documents_lower_developer_name "
        "ON search_index_documents (organization_id, lower(developer_name))",
    )
    op.execute(
        "CREATE INDEX ix_search_index_documents_lower_display_name "
        "ON search_index_documents (organization_id, lower(display_name))",
    )


def downgrade() -> None:
    op.drop_table("search_index_documents")
