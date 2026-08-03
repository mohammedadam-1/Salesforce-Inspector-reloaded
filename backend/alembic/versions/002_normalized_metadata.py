"""Create normalized metadata component tables.

Revision ID: 002
Revises: 001
Create Date: 2026-07-16
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: str = "001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    # --- metadata_objects ---
    op.create_table(
        "metadata_objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("plural_label", sa.String(256), server_default=""),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("namespace", sa.String(128), nullable=True),
        sa.Column("sharing_model", sa.String(64), server_default="ReadWrite"),
        sa.Column("deployment_status", sa.String(32), server_default="Deployed"),
        sa.Column("enable_feeds", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("enable_history", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("enable_reports", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("enable_search", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("enable_sharing", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("enable_bulk_api", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("enable_streaming_api", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("enable_enhanced_lookup", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_custom", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_deprecated_and_hidden", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("key_prefix", sa.String(8), nullable=True),
        sa.Column("created_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_modified_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_fields ---
    op.create_table(
        "metadata_fields",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_objects.id"), nullable=False, index=True),
        sa.Column("object_api_name", sa.String(256), nullable=False),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("field_type", sa.String(64), nullable=False),
        sa.Column("length", sa.Integer(), nullable=True),
        sa.Column("precision", sa.Integer(), nullable=True),
        sa.Column("scale", sa.Integer(), nullable=True),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("unique", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("external_id", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("picklist_values", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("relationship_name", sa.String(256), nullable=True),
        sa.Column("reference_to", sa.String(256), nullable=True),
        sa.Column("cascade_delete", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("formula_treat_blanks_as", sa.String(32), nullable=True),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("business_owner_group", sa.String(256), nullable=True),
        sa.Column("business_owner_user", sa.String(256), nullable=True),
        sa.Column("compliance", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("tracked_history", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_custom", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("is_deprecated_and_hidden", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_validation_rules ---
    op.create_table(
        "metadata_validation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_objects.id"), nullable=False, index=True),
        sa.Column("object_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("error_message", sa.Text(), server_default=""),
        sa.Column("error_display_field", sa.String(256), nullable=True),
        sa.Column("formula", sa.Text(), server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_record_types ---
    op.create_table(
        "metadata_record_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metadata_objects.id"), nullable=False, index=True),
        sa.Column("object_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("business_process", sa.String(256), nullable=True),
        sa.Column("compact_layout_assignment", sa.String(256), nullable=True),
        sa.Column("picklist_values", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_apex_classes ---
    op.create_table(
        "metadata_apex_classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("api_version", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), server_default=""),
        sa.Column("body_length", sa.Integer(), nullable=True),
        sa.Column("package_versions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("urls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_valid", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("status", sa.String(32), server_default="Active"),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_triggers ---
    op.create_table(
        "metadata_triggers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("object_api_name", sa.String(256), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("api_version", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), server_default=""),
        sa.Column("trigger_events", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("usage_after_insert", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_after_update", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_before_insert", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_before_update", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_after_delete", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_before_delete", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_is_bulk", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("usage_is_recursive", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("status", sa.String(32), server_default="Active"),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_flows ---
    op.create_table(
        "metadata_flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("namespace", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("process_type", sa.String(64), server_default="Flow"),
        sa.Column("flow_status", sa.String(32), server_default="Draft"),
        sa.Column("version_number", sa.Integer(), server_default=sa.text("1")),
        sa.Column("api_version", sa.Integer(), nullable=True),
        sa.Column("interview_label", sa.String(256), nullable=True),
        sa.Column("run_in_mode", sa.String(64), server_default="SystemModeWithoutSharing"),
        sa.Column("variables", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("stages", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("elements", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("record_creates", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("record_updates", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("record_deletes", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("subflows", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_layouts ---
    op.create_table(
        "metadata_layouts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("object_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("layout_type", sa.String(32), server_default="Detail"),
        sa.Column("sections", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("related_lists", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("mini_layout", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("quick_actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("summary_layout", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("headings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_profiles ---
    op.create_table(
        "metadata_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("user_license", sa.String(128), server_default=""),
        sa.Column("custom", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("object_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("field_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("class_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("page_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("user_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("record_type_visibilities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("login_hours", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("login_ip_ranges", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_permission_sets ---
    op.create_table(
        "metadata_permission_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("user_license", sa.String(128), server_default=""),
        sa.Column("is_owned_by_profile", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("profile_name", sa.String(256), nullable=True),
        sa.Column("has_activation", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("object_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("field_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("class_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("page_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("user_permissions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("record_type_visibilities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("login_hours", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("login_ip_ranges", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_reports ---
    op.create_table(
        "metadata_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("report_type", sa.String(128), nullable=True),
        sa.Column("folder_name", sa.String(256), nullable=True),
        sa.Column("owner_id", sa.String(256), nullable=True),
        sa.Column("last_run_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("columns", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("filters", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("groupings", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_dashboards ---
    op.create_table(
        "metadata_dashboards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("folder_name", sa.String(256), nullable=True),
        sa.Column("owner_id", sa.String(256), nullable=True),
        sa.Column("dashboard_type", sa.String(64), nullable=True),
        sa.Column("components", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("filters", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_workflow_rules ---
    op.create_table(
        "metadata_workflow_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("object_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("api_name", sa.String(256), nullable=False, index=True),
        sa.Column("label", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("trigger_type", sa.String(64), server_default="onCreateOrTriggeringUpdate"),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_relationships ---
    op.create_table(
        "metadata_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("source_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("target_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("relationship_type", sa.String(32), server_default="lookup"),
        sa.Column("cascade_delete", sa.Boolean(), server_default=sa.text("false")),
        sa.Column("junction_object", sa.String(256), nullable=True),
        sa.Column("field_api_name", sa.String(256), nullable=True),
        sa.Column("fingerprint", sa.String(64), server_default=""),
        sa.Column("metadata_properties", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- metadata_dependencies ---
    op.create_table(
        "metadata_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("source_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("target_api_name", sa.String(256), nullable=False, index=True),
        sa.Column("target_type", sa.String(64), nullable=False),
        sa.Column("dependency_type", sa.String(64), nullable=False, index=True),
        sa.Column("source_field", sa.String(256), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("graph_version", sa.String(64), server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- search_documents ---
    op.create_table(
        "search_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False, index=True),
        sa.Column("component_type", sa.String(128), nullable=False, index=True),
        sa.Column("component_name", sa.String(256), nullable=False, index=True),
        sa.Column("component_id", sa.String(256), nullable=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("content", sa.Text(), server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("namespace", sa.String(128), nullable=True),
        sa.Column("object_api_name", sa.String(256), nullable=True),
        sa.Column("tags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("search_vector", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- indexes ---
    op.create_index("ix_metadata_objects_api_name", "metadata_objects", ["api_name"])
    op.create_index("ix_metadata_objects_org_api_name", "metadata_objects", ["organization_id", "api_name"])
    op.create_index("ix_metadata_fields_org_api_name", "metadata_fields", ["organization_id", "api_name"])
    op.create_index("ix_metadata_fields_object_api_name", "metadata_fields", ["object_api_name"])
    op.create_index("ix_metadata_validation_rules_org_api_name", "metadata_validation_rules", ["organization_id", "api_name"])
    op.create_index("ix_metadata_validation_rules_formula", "metadata_validation_rules", ["formula"], postgresql_using="gin", postgresql_ops={"formula": "gin_trgm_ops"})
    op.create_index("ix_metadata_triggers_object_api_name", "metadata_triggers", ["object_api_name"])
    op.create_index("ix_metadata_flows_org_api_name", "metadata_flows", ["organization_id", "api_name"])
    op.create_index("ix_metadata_layouts_org_object", "metadata_layouts", ["organization_id", "object_api_name"])
    op.create_index("ix_metadata_profiles_org_api_name", "metadata_profiles", ["organization_id", "api_name"])
    op.create_index("ix_metadata_permission_sets_org_api_name", "metadata_permission_sets", ["organization_id", "api_name"])
    op.create_index("ix_metadata_dependencies_org_source", "metadata_dependencies", ["organization_id", "source_api_name"])
    op.create_index("ix_metadata_dependencies_org_target", "metadata_dependencies", ["organization_id", "target_api_name"])
    op.create_index("ix_search_documents_org_type", "search_documents", ["organization_id", "component_type"])
    op.create_index("ix_search_documents_title_trgm", "search_documents", ["title"], postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"})
    op.create_index("ix_metadata_relationships_org_source", "metadata_relationships", ["organization_id", "source_api_name"])
    op.create_index("ix_metadata_workflow_rules_org_api_name", "metadata_workflow_rules", ["organization_id", "api_name"])


def downgrade() -> None:
    op.drop_table("search_documents")
    op.drop_table("metadata_dependencies")
    op.drop_table("metadata_relationships")
    op.drop_table("metadata_workflow_rules")
    op.drop_table("metadata_dashboards")
    op.drop_table("metadata_reports")
    op.drop_table("metadata_permission_sets")
    op.drop_table("metadata_profiles")
    op.drop_table("metadata_layouts")
    op.drop_table("metadata_flows")
    op.drop_table("metadata_triggers")
    op.drop_table("metadata_apex_classes")
    op.drop_table("metadata_record_types")
    op.drop_table("metadata_validation_rules")
    op.drop_table("metadata_fields")
    op.drop_table("metadata_objects")
