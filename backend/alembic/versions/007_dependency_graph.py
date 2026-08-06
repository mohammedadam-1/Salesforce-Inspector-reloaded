"""Dependency graph store — graph nodes and edges derived from canonical data.

Adds graph_nodes and graph_edges: the persisted dependency graph. One node
per canonical document identity per tenant, keyed by (organization_id,
identity); one edge per canonical relationship per tenant, keyed by
(organization_id, source_identity, target_identity, relationship_type).
Both are versioned and soft-deleted, never physically removed, so the
graph can be rebuilt incrementally and safely under concurrent workers.

Revision ID: 007
Revises: 006
Create Date: 2026-08-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "007"
down_revision: str = "006"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "graph_nodes",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column(
            "organization_id",
            UUID(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("identity", sa.String(64), nullable=False),
        sa.Column("type", sa.String(128), nullable=False),
        sa.Column("api_name", sa.String(512), nullable=False, server_default=""),
        sa.Column("namespace", sa.String(256), nullable=True),
        sa.Column("document_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "document_fingerprint",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
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
            name="uq_graph_nodes_org_identity",
        ),
    )
    op.create_index(
        "ix_graph_nodes_organization_id",
        "graph_nodes",
        ["organization_id"],
    )
    op.create_index(
        "ix_graph_nodes_identity",
        "graph_nodes",
        ["identity"],
    )
    op.create_index(
        "ix_graph_nodes_type",
        "graph_nodes",
        ["type"],
    )
    op.create_table(
        "graph_edges",
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
            name="uq_graph_edges_src_tgt_type",
        ),
    )
    op.create_index(
        "ix_graph_edges_organization_id",
        "graph_edges",
        ["organization_id"],
    )
    op.create_index(
        "ix_graph_edges_source_identity",
        "graph_edges",
        ["source_identity"],
    )
    op.create_index(
        "ix_graph_edges_target_identity",
        "graph_edges",
        ["target_identity"],
    )
    op.create_index(
        "ix_graph_edges_relationship_type",
        "graph_edges",
        ["relationship_type"],
    )


def downgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
