"""Initial production database schema.

Revision ID: 0001_initial_database
Revises:
Create Date: 2026-07-04 00:00:00.000000+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_database"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        UUID,
        primary_key=True,
        nullable=False,
        server_default=sa.text("gen_random_uuid()"),
    )


def timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def jsonb_column(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, JSONB, nullable=nullable, server_default=sa.text("'{}'::jsonb"))


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "users",
        uuid_pk(),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("external_subject", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_service_account", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.UniqueConstraint("external_subject", name="uq_users_external_subject"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "roles",
        uuid_pk(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *timestamps(),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )

    op.create_table(
        "permissions",
        uuid_pk(),
        sa.Column("code", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )

    op.create_table(
        "organizations",
        uuid_pk(),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=160), nullable=False),
        sa.Column("salesforce_org_id", sa.String(length=18), nullable=True),
        sa.Column("instance_url", sa.String(length=512), nullable=True),
        sa.Column("environment", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("settings"),
        *timestamps(),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        sa.UniqueConstraint("salesforce_org_id", name="uq_organizations_salesforce_org_id"),
    )
    op.create_index("ix_organizations_salesforce_org_id", "organizations", ["salesforce_org_id"])
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID, nullable=False),
        sa.Column("permission_id", UUID, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
        sa.UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
    )

    op.create_table(
        "organization_memberships",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("invited_by_user_id", UUID, nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_organization_membership"),
    )
    op.create_index(
        "ix_org_memberships_org_status", "organization_memberships", ["organization_id", "status"]
    )

    op.create_table(
        "user_roles",
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("role_id", UUID, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "organization_id", "role_id"),
        sa.UniqueConstraint("user_id", "organization_id", "role_id", name="uq_user_org_role"),
    )
    op.create_index("ix_user_roles_user_org", "user_roles", ["user_id", "organization_id"])

    op.create_table(
        "api_keys",
        uuid_pk(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=False),
        jsonb_column("scopes"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_key_prefix", "api_keys", ["key_prefix"])
    op.create_index("ix_api_keys_user_org", "api_keys", ["user_id", "organization_id"])

    op.create_table(
        "salesforce_connections",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("connected_by_user_id", UUID, nullable=True),
        sa.Column("connection_type", sa.String(length=40), nullable=False),
        sa.Column("salesforce_org_id", sa.String(length=18), nullable=False),
        sa.Column("instance_url", sa.String(length=512), nullable=False),
        sa.Column("login_url", sa.String(length=512), nullable=False),
        sa.Column("api_version", sa.String(length=12), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("scopes"),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connected_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("organization_id", "connection_type", name="uq_salesforce_connection_type"),
    )
    op.create_index(
        "ix_salesforce_connections_org_status", "salesforce_connections", ["organization_id", "status"]
    )

    op.create_table(
        "salesforce_api_usage",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("api_family", sa.String(length=40), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_salesforce_api_usage_org_window",
        "salesforce_api_usage",
        ["organization_id", "window_started_at"],
    )
    op.create_index(
        "ix_salesforce_api_usage_endpoint",
        "salesforce_api_usage",
        ["organization_id", "api_family", "endpoint"],
    )

    op.create_table(
        "metadata_sync_runs",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("sync_type", sa.String(length=40), nullable=False),
        sa.Column("api_version", sa.String(length=12), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        jsonb_column("stats"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_metadata_sync_runs_org_status", "metadata_sync_runs", ["organization_id", "status"]
    )

    op.create_table(
        "metadata_components",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("parent_component_id", UUID, nullable=True),
        sa.Column("component_type", sa.String(length=80), nullable=False),
        sa.Column("api_name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=True),
        sa.Column("namespace_prefix", sa.String(length=80), nullable=False, server_default=""),
        sa.Column("salesforce_id", sa.String(length=18), nullable=True),
        sa.Column("durable_id", sa.String(length=255), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("api_version", sa.String(length=12), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("extra"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "component_type",
            "full_name",
            "namespace_prefix",
            name="uq_metadata_component_identity",
        ),
    )
    op.create_index(
        "ix_metadata_components_org_type",
        "metadata_components",
        ["organization_id", "component_type"],
    )
    op.create_index(
        "ix_metadata_components_org_api_name",
        "metadata_components",
        ["organization_id", "api_name"],
    )
    op.create_index("ix_metadata_components_parent", "metadata_components", ["parent_component_id"])
    op.create_index(
        "ix_metadata_components_salesforce_id",
        "metadata_components",
        ["organization_id", "salesforce_id"],
    )

    op.create_table(
        "metadata_fields",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("component_id", UUID, nullable=False),
        sa.Column("api_name", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=512), nullable=True),
        sa.Column("data_type", sa.String(length=80), nullable=False),
        sa.Column("relationship_name", sa.String(length=255), nullable=True),
        jsonb_column("reference_to"),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_formula", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_unique", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_external_id", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("inline_help_text", sa.Text(), nullable=True),
        jsonb_column("extra"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("component_id", "api_name", name="uq_metadata_field_component_api_name"),
    )
    op.create_index(
        "ix_metadata_fields_org_component", "metadata_fields", ["organization_id", "component_id"]
    )
    op.create_index("ix_metadata_fields_org_api_name", "metadata_fields", ["organization_id", "api_name"])
    op.create_index("ix_metadata_fields_data_type", "metadata_fields", ["organization_id", "data_type"])

    op.create_table(
        "metadata_versions",
        uuid_pk(),
        sa.Column("component_id", UUID, nullable=False),
        sa.Column("sync_run_id", UUID, nullable=True),
        sa.Column("version_label", sa.String(length=120), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        jsonb_column("payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["metadata_sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_metadata_versions_component_version", "metadata_versions", ["component_id", "version_label"]
    )

    op.create_table(
        "metadata_raw_payloads",
        uuid_pk(),
        sa.Column("component_id", UUID, nullable=False),
        sa.Column("sync_run_id", UUID, nullable=True),
        sa.Column("source_api", sa.String(length=40), nullable=False),
        sa.Column("payload_hash", sa.String(length=128), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["metadata_sync_runs.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_metadata_raw_payloads_component_source",
        "metadata_raw_payloads",
        ["component_id", "source_api"],
    )

    op.create_table(
        "dependency_edges",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("source_component_id", UUID, nullable=True),
        sa.Column("target_component_id", UUID, nullable=True),
        sa.Column("edge_type", sa.String(length=80), nullable=False),
        sa.Column("source_key", sa.String(length=768), nullable=False),
        sa.Column("target_key", sa.String(length=768), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("source_api", sa.String(length=40), nullable=True),
        jsonb_column("evidence"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_component_id"], ["metadata_components.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "organization_id",
            "source_component_id",
            "target_component_id",
            "edge_type",
            "source_key",
            "target_key",
            name="uq_dependency_edge_identity",
        ),
    )
    op.create_index(
        "ix_dependency_edges_source",
        "dependency_edges",
        ["organization_id", "source_component_id", "edge_type"],
    )
    op.create_index(
        "ix_dependency_edges_target",
        "dependency_edges",
        ["organization_id", "target_component_id", "edge_type"],
    )
    op.create_index(
        "ix_dependency_edges_keys", "dependency_edges", ["organization_id", "source_key", "target_key"]
    )

    op.create_table(
        "dependency_snapshots",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("root_component_id", UUID, nullable=True),
        sa.Column("root_key", sa.String(length=768), nullable=False),
        sa.Column("traversal_direction", sa.String(length=40), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("graph_hash", sa.String(length=128), nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["root_component_id"], ["metadata_components.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_dependency_snapshots_org_component",
        "dependency_snapshots",
        ["organization_id", "root_key"],
    )

    op.create_table(
        "ai_conversations",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("created_by_user_id", UUID, nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("metadata_scope"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ai_conversations_org_user", "ai_conversations", ["organization_id", "created_by_user_id"]
    )

    op.create_table(
        "ai_messages",
        uuid_pk(),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        jsonb_column("citations"),
        sa.Column("safety_status", sa.String(length=40), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_messages_conversation_created", "ai_messages", ["conversation_id", "created_at"])

    op.create_table(
        "prompt_history",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("ai_message_id", UUID, nullable=True),
        sa.Column("template_name", sa.String(length=160), nullable=False),
        sa.Column("template_version", sa.String(length=80), nullable=False),
        sa.Column("llm_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("prompt_hash", sa.String(length=128), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("prompt_payload", JSONB, nullable=False),
        jsonb_column("response_payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ai_message_id"], ["ai_messages.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_prompt_history_org_template", "prompt_history", ["organization_id", "template_name"])
    op.create_index("ix_prompt_history_message", "prompt_history", ["ai_message_id"])

    op.create_table(
        "retrieval_contexts",
        uuid_pk(),
        sa.Column("ai_message_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=80), nullable=False),
        jsonb_column("component_ids"),
        sa.Column("query_payload", JSONB, nullable=False),
        sa.Column("context_payload", JSONB, nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["ai_message_id"], ["ai_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_retrieval_contexts_message", "retrieval_contexts", ["ai_message_id"])

    op.create_table(
        "action_plans",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("risk_level", sa.String(length=40), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("plan_payload", JSONB, nullable=False),
        jsonb_column("safety_report"),
        jsonb_column("rollback_plan"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["ai_conversations.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_action_plans_org_status", "action_plans", ["organization_id", "status"])

    op.create_table(
        "action_steps",
        uuid_pk(),
        sa.Column("action_plan_id", UUID, nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("target_type", sa.String(length=120), nullable=False),
        sa.Column("target_full_name", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("diff_payload", JSONB, nullable=False),
        jsonb_column("validation_payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["action_plan_id"], ["action_plans.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_action_steps_plan_order", "action_steps", ["action_plan_id", "step_order"])

    op.create_table(
        "approvals",
        uuid_pk(),
        sa.Column("action_plan_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("decided_by_user_id", UUID, nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["action_plan_id"], ["action_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_approvals_action_status", "approvals", ["action_plan_id", "status"])

    op.create_table(
        "deployments",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("action_plan_id", UUID, nullable=True),
        sa.Column("requested_by_user_id", UUID, nullable=False),
        sa.Column("salesforce_deploy_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("check_only", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        jsonb_column("result_payload"),
        sa.Column("error_message", sa.Text(), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["action_plan_id"], ["action_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_deployments_org_status", "deployments", ["organization_id", "status"])
    op.create_index("ix_deployments_salesforce_deploy_id", "deployments", ["salesforce_deploy_id"])

    op.create_table(
        "deployment_artifacts",
        uuid_pk(),
        sa.Column("deployment_id", UUID, nullable=False),
        sa.Column("artifact_kind", sa.String(length=80), nullable=False),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        jsonb_column("payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_deployment_artifacts_deployment_kind",
        "deployment_artifacts",
        ["deployment_id", "artifact_kind"],
    )

    op.create_table(
        "deployment_verifications",
        uuid_pk(),
        sa.Column("deployment_id", UUID, nullable=False),
        sa.Column("verification_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        jsonb_column("details"),
        *timestamps(),
        sa.ForeignKeyConstraint(["deployment_id"], ["deployments.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_deployment_verifications_deployment",
        "deployment_verifications",
        ["deployment_id", "status"],
    )

    op.create_table(
        "background_jobs",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("requested_by_user_id", UUID, nullable=True),
        sa.Column("job_type", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("progress_current", sa.Integer(), nullable=False),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        jsonb_column("payload"),
        jsonb_column("result"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("celery_task_id", name="uq_background_jobs_celery_task_id"),
    )
    op.create_index("ix_background_jobs_org_status", "background_jobs", ["organization_id", "status"])
    op.create_index("ix_background_jobs_celery_task", "background_jobs", ["celery_task_id"])

    op.create_table(
        "job_events",
        uuid_pk(),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        jsonb_column("payload"),
        *timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["background_jobs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_job_events_job_created", "job_events", ["job_id", "created_at"])

    op.create_table(
        "job_cancellations",
        uuid_pk(),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("requested_by_user_id", UUID, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.ForeignKeyConstraint(["job_id"], ["background_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_job_cancellations_job", "job_cancellations", ["job_id"])

    op.create_table(
        "audit_logs",
        uuid_pk(),
        sa.Column("organization_id", UUID, nullable=True),
        sa.Column("actor_user_id", UUID, nullable=True),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("resource_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        jsonb_column("before_state"),
        jsonb_column("after_state"),
        jsonb_column("details"),
        *timestamps(),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_org_created", "audit_logs", ["organization_id", "created_at"])
    op.create_index("ix_audit_logs_actor_created", "audit_logs", ["actor_user_id", "created_at"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("job_cancellations")
    op.drop_table("job_events")
    op.drop_table("background_jobs")
    op.drop_table("deployment_verifications")
    op.drop_table("deployment_artifacts")
    op.drop_table("deployments")
    op.drop_table("approvals")
    op.drop_table("action_steps")
    op.drop_table("action_plans")
    op.drop_table("retrieval_contexts")
    op.drop_table("prompt_history")
    op.drop_table("ai_messages")
    op.drop_table("ai_conversations")
    op.drop_table("dependency_snapshots")
    op.drop_table("dependency_edges")
    op.drop_table("metadata_raw_payloads")
    op.drop_table("metadata_versions")
    op.drop_table("metadata_fields")
    op.drop_table("metadata_components")
    op.drop_table("metadata_sync_runs")
    op.drop_table("salesforce_api_usage")
    op.drop_table("salesforce_connections")
    op.drop_table("api_keys")
    op.drop_table("user_roles")
    op.drop_table("organization_memberships")
    op.drop_table("role_permissions")
    op.drop_table("organizations")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("users")

