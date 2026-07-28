"""Initial schema: create all tables.

Revision ID: 001
Revises:
Create Date: 2026-07-16
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(320), nullable=False, unique=True, index=True),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active", index=True),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("login_attempts", sa.Integer(), server_default=sa.text("0")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- organizations ---
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active", index=True),
        sa.Column("settings", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("slug", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- permissions ---
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False, index=True),
        sa.Column("permission_slug", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- salesforce_connections ---
    op.create_table(
        "salesforce_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("environment", sa.String(32), nullable=False, server_default="production"),
        sa.Column("instance_url", sa.String(512), nullable=False),
        sa.Column("org_id", sa.String(32), nullable=False, index=True),
        sa.Column("username", sa.String(256), nullable=False),
        sa.Column("api_version", sa.String(8), nullable=False, server_default="62.0"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending", index=True),
        sa.Column("access_token_encrypted", sa.Text(), server_default=""),
        sa.Column("refresh_token_encrypted", sa.Text(), server_default=""),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failed_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- sync_jobs ---
    op.create_table(
        "sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("salesforce_connections.id"), nullable=False, index=True),
        sa.Column("sync_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending", index=True),
        sa.Column("metadata_type", sa.String(128), nullable=True),
        sa.Column("progress", sa.Float(), server_default=sa.text("0.0")),
        sa.Column("total_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("processed_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("failed_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- org_members ---
    op.create_table(
        "org_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- refresh_tokens ---
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_revoked", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("refresh_token_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("refresh_tokens.id"), nullable=True),
        sa.Column("ip_address", sa.String(45), server_default=""),
        sa.Column("user_agent", sa.Text(), server_default=""),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True, index=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=True, index=True),
        sa.Column("action", sa.String(64), nullable=False, index=True),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(256), nullable=False),
        sa.Column("details", postgresql.JSONB(), nullable=True),
        sa.Column("ip_address", sa.String(45), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), index=True),
    )

    # --- metadata_versions ---
    op.create_table(
        "metadata_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False, index=True),
        sa.Column("component_type", sa.String(128), nullable=False, index=True),
        sa.Column("component_name", sa.String(256), nullable=False),
        sa.Column("component_id", sa.String(256), nullable=True),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("payload", postgresql.JSON(), nullable=True),
        sa.Column("salesforce_last_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("change_source", sa.String(64), server_default="sync"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- sync_history ---
    op.create_table(
        "sync_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("salesforce_connections.id"), nullable=False, index=True),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=True),
        sa.Column("sync_type", sa.String(24), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("total_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("processed_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("failed_items", sa.Integer(), server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- sync_retry_queue ---
    op.create_table(
        "sync_retry_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("sync_job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("sync_jobs.id"), nullable=False, index=True),
        sa.Column("component_type", sa.String(128), nullable=False),
        sa.Column("component_name", sa.String(256), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), server_default=sa.text("3")),
        sa.Column("last_error", sa.Text(), server_default=""),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- sync_statistics ---
    op.create_table(
        "sync_statistics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("salesforce_connections.id"), nullable=False, unique=True, index=True),
        sa.Column("total_syncs", sa.Integer(), server_default=sa.text("0")),
        sa.Column("successful_syncs", sa.Integer(), server_default=sa.text("0")),
        sa.Column("failed_syncs", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_components_synced", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_components_created", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_components_updated", sa.Integer(), server_default=sa.text("0")),
        sa.Column("total_components_deleted", sa.Integer(), server_default=sa.text("0")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- composite indexes ---
    op.create_index("ix_sync_jobs_org_status", "sync_jobs", ["organization_id", "status"])
    op.create_index("ix_metadata_versions_org_type", "metadata_versions", ["organization_id", "component_type"])
    op.create_index("ix_audit_logs_org_action", "audit_logs", ["organization_id", "action"])
    op.create_index("ix_sync_history_job_id", "sync_history", ["sync_job_id"])
    op.create_index("ix_metadata_versions_component_name", "metadata_versions", ["component_name"])
    op.create_index("ix_sync_retry_queue_next_retry", "sync_retry_queue", ["next_retry_at"])


def downgrade() -> None:
    op.drop_table("sync_statistics")
    op.drop_table("sync_retry_queue")
    op.drop_table("sync_history")
    op.drop_table("metadata_versions")
    op.drop_table("audit_logs")
    op.drop_table("sessions")
    op.drop_table("refresh_tokens")
    op.drop_table("org_members")
    op.drop_table("sync_jobs")
    op.drop_table("salesforce_connections")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("organizations")
    op.drop_table("users")
