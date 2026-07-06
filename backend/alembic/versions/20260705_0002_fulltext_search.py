"""Add full-text search indexes and performance optimizations.

Revision ID: 0002_fulltext_search
Revises: 0001_initial_database
Create Date: 2026-07-05 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_fulltext_search"
down_revision: str = "0001_initial_database"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Full-text search for metadata components ---
    op.execute(
        """
        ALTER TABLE metadata_components
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(api_name, '') || ' ' ||
                coalesce(label, '') || ' ' ||
                coalesce(full_name, '') || ' ' ||
                coalesce(component_type, '')
            )
        ) STORED;
        """
    )
    op.create_index(
        "ix_metadata_components_search",
        "metadata_components",
        ["search_vector"],
        postgresql_using="gin",
    )

    # --- Full-text search for metadata fields ---
    op.execute(
        """
        ALTER TABLE metadata_fields
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(api_name, '') || ' ' ||
                coalesce(label, '') || ' ' ||
                coalesce(data_type, '') || ' ' ||
                coalesce(inline_help_text, '')
            )
        ) STORED;
        """
    )
    op.create_index(
        "ix_metadata_fields_search",
        "metadata_fields",
        ["search_vector"],
        postgresql_using="gin",
    )

    # --- GIN indexes for JSONB columns commonly queried ---
    op.create_index(
        "ix_metadata_components_extra",
        "metadata_components",
        ["extra"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_action_plans_plan_payload",
        "action_plans",
        ["plan_payload"],
        postgresql_using="gin",
    )

    # --- Performance indexes for common query patterns ---

    # Audit log time-range queries
    op.create_index(
        "ix_audit_logs_occurred_at_action",
        "audit_logs",
        ["occurred_at", "action"],
        postgresql_using="btree",
    )

    # Background job queue processing
    op.create_index(
        "ix_background_jobs_status_type_created",
        "background_jobs",
        ["status", "job_type", "created_at"],
        postgresql_using="btree",
    )

    # Action step processing queue
    op.create_index(
        "ix_action_steps_status_plan",
        "action_steps",
        ["status", "action_plan_id"],
        postgresql_using="btree",
    )

    # Deployment lookup by org + status + created_at
    op.create_index(
        "ix_deployments_org_status_created",
        "deployments",
        ["organization_id", "status", "created_at"],
        postgresql_using="btree",
    )

    # Metadata sync runs lookup
    op.create_index(
        "ix_metadata_sync_runs_org_created",
        "metadata_sync_runs",
        ["organization_id", "created_at"],
        postgresql_using="btree",
    )

    # Dependency edges by source/target key prefix for prefix searches
    op.create_index(
        "ix_dependency_edges_source_key_prefix",
        "dependency_edges",
        ["source_key"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_dependency_edges_target_key_prefix",
        "dependency_edges",
        ["target_key"],
        postgresql_using="btree",
    )

    # Salesforce API usage cleanup queries
    op.create_index(
        "ix_salesforce_api_usage_window",
        "salesforce_api_usage",
        ["window_started_at"],
        postgresql_using="btree",
    )

    # AI conversations for user dashboard
    op.create_index(
        "ix_ai_conversations_user_status",
        "ai_conversations",
        ["created_by_user_id", "status"],
        postgresql_using="btree",
    )


def downgrade() -> None:
    # Drop full-text search indexes
    op.drop_index("ix_metadata_components_search", table_name="metadata_components")
    op.drop_index("ix_metadata_fields_search", table_name="metadata_fields")
    op.drop_column("metadata_components", "search_vector")
    op.drop_column("metadata_fields", "search_vector")

    # Drop JSONB GIN indexes
    op.drop_index("ix_metadata_components_extra", table_name="metadata_components")
    op.drop_index("ix_action_plans_plan_payload", table_name="action_plans")

    # Drop performance indexes
    op.drop_index("ix_audit_logs_occurred_at_action", table_name="audit_logs")
    op.drop_index("ix_background_jobs_status_type_created", table_name="background_jobs")
    op.drop_index("ix_action_steps_status_plan", table_name="action_steps")
    op.drop_index("ix_deployments_org_status_created", table_name="deployments")
    op.drop_index("ix_metadata_sync_runs_org_created", table_name="metadata_sync_runs")
    op.drop_index("ix_dependency_edges_source_key_prefix", table_name="dependency_edges")
    op.drop_index("ix_dependency_edges_target_key_prefix", table_name="dependency_edges")
    op.drop_index("ix_salesforce_api_usage_window", table_name="salesforce_api_usage")
    op.drop_index("ix_ai_conversations_user_status", table_name="ai_conversations")
