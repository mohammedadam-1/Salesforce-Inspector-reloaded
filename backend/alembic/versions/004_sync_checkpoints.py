"""Durable sync checkpoints for batched metadata retrieval.

Adds the per-batch checkpoint table used by the metadata sync worker
so a sync resumes from the last successful batch instead of restarting:

- sync_job_id        the owning sync job
- metadata_type      the metadata type being retrieved
- batch_id           1-based deterministic batch ordinal
- cursor             resume token: last component key of the prior batch
- status             completed / failed
- retry_count        number of failed attempts for the batch
- UNIQUE (sync_job_id, metadata_type, batch_id)

Revision ID: 004
Revises: 003
Create Date: 2026-08-05
"""

import sqlalchemy as sa

from alembic import op

revision: str = "004"
down_revision: str = "003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "sync_checkpoints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "sync_job_id",
            sa.Uuid(),
            sa.ForeignKey("sync_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("metadata_type", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("cursor", sa.String(1024), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="completed"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
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
        sa.UniqueConstraint(
            "sync_job_id", "metadata_type", "batch_id",
            name="uq_sync_checkpoints_job_type_batch",
        ),
    )
    op.create_index(
        "ix_sync_checkpoints_sync_job_id",
        "sync_checkpoints",
        ["sync_job_id"],
    )
    op.create_index(
        "ix_sync_checkpoints_organization_id",
        "sync_checkpoints",
        ["organization_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_sync_checkpoints_organization_id", table_name="sync_checkpoints")
    op.drop_index("ix_sync_checkpoints_sync_job_id", table_name="sync_checkpoints")
    op.drop_table("sync_checkpoints")
