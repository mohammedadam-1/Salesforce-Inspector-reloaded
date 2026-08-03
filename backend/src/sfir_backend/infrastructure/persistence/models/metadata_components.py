"""Normalized metadata component SQLAlchemy models.

Provides dedicated tables for each metadata component type,
enabling normalized storage instead of raw Salesforce JSON.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from sfir_backend.infrastructure.database.base import Base


class MetadataObjectModel(Base):
    """Normalized Salesforce Object (sObject) storage."""

    __tablename__ = "metadata_objects"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    plural_label: Mapped[str] = mapped_column(String(256), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sharing_model: Mapped[str] = mapped_column(String(64), default="ReadWrite")
    deployment_status: Mapped[str] = mapped_column(String(32), default="Deployed")
    enable_feeds: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_history: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_reports: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_search: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_sharing: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_bulk_api: Mapped[bool] = mapped_column(Boolean, default=True)
    enable_streaming_api: Mapped[bool] = mapped_column(Boolean, default=False)
    enable_enhanced_lookup: Mapped[bool] = mapped_column(Boolean, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deprecated_and_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    key_prefix: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_modified_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )

    fields = relationship("MetadataFieldModel", back_populates="object_", lazy="selectin",
                          cascade="all, delete-orphan")
    validation_rules = relationship("MetadataValidationRuleModel", back_populates="object_",
                                     lazy="selectin", cascade="all, delete-orphan")
    record_types = relationship("MetadataRecordTypeModel", back_populates="object_",
                                 lazy="selectin", cascade="all, delete-orphan")


class MetadataFieldModel(Base):
    """Normalized Salesforce Field storage."""

    __tablename__ = "metadata_fields"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_objects.id"), nullable=True, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    field_type: Mapped[str] = mapped_column(String(64), nullable=False)
    length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scale: Mapped[int | None] = mapped_column(Integer, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    unique: Mapped[bool] = mapped_column(Boolean, default=False)
    external_id: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    picklist_values: Mapped[list] = mapped_column(JSONB, default=list)
    relationship_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reference_to: Mapped[str | None] = mapped_column(String(256), nullable=True)
    cascade_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_treat_blanks_as: Mapped[str | None] = mapped_column(String(32), nullable=True)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_owner_group: Mapped[str | None] = mapped_column(String(256), nullable=True)
    business_owner_user: Mapped[str | None] = mapped_column(String(256), nullable=True)
    compliance: Mapped[bool] = mapped_column(Boolean, default=False)
    tracked_history: Mapped[bool] = mapped_column(Boolean, default=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_deprecated_and_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )

    object_ = relationship("MetadataObjectModel", back_populates="fields")


class MetadataValidationRuleModel(Base):
    """Normalized Salesforce Validation Rule storage."""

    __tablename__ = "metadata_validation_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_objects.id"), nullable=True, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    error_message: Mapped[str] = mapped_column(Text, default="")
    error_display_field: Mapped[str | None] = mapped_column(String(256), nullable=True)
    formula: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )

    object_ = relationship("MetadataObjectModel", back_populates="validation_rules")


class MetadataRecordTypeModel(Base):
    """Normalized Salesforce Record Type storage."""

    __tablename__ = "metadata_record_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metadata_objects.id"), nullable=True, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    business_process: Mapped[str | None] = mapped_column(String(256), nullable=True)
    compact_layout_assignment: Mapped[str | None] = mapped_column(String(256), nullable=True)
    picklist_values: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )

    object_ = relationship("MetadataObjectModel", back_populates="record_types")


class MetadataApexClassModel(Base):
    """Normalized Salesforce Apex Class storage."""

    __tablename__ = "metadata_apex_classes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    body_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    package_versions: Mapped[list] = mapped_column(JSONB, default=list)
    urls: Mapped[list] = mapped_column(JSONB, default=list)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(32), default="Active")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataTriggerModel(Base):
    """Normalized Salesforce Apex Trigger storage."""

    __tablename__ = "metadata_triggers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    body: Mapped[str] = mapped_column(Text, default="")
    trigger_events: Mapped[list] = mapped_column(JSONB, default=list)
    usage_after_insert: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_after_update: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_before_insert: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_before_update: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_after_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_before_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_is_bulk: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_is_recursive: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(32), default="Active")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataFlowModel(Base):
    """Normalized Salesforce Flow storage."""

    __tablename__ = "metadata_flows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    process_type: Mapped[str] = mapped_column(String(64), default="Flow")
    flow_status: Mapped[str] = mapped_column(String(32), default="Draft")
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    api_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interview_label: Mapped[str | None] = mapped_column(String(256), nullable=True)
    run_in_mode: Mapped[str] = mapped_column(String(64), default="SystemModeWithoutSharing")
    variables: Mapped[list] = mapped_column(JSONB, default=list)
    stages: Mapped[list] = mapped_column(JSONB, default=list)
    elements: Mapped[list] = mapped_column(JSONB, default=list)
    record_creates: Mapped[list] = mapped_column(JSONB, default=list)
    record_updates: Mapped[list] = mapped_column(JSONB, default=list)
    record_deletes: Mapped[list] = mapped_column(JSONB, default=list)
    subflows: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataLayoutModel(Base):
    """Normalized Salesforce Layout storage."""

    __tablename__ = "metadata_layouts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    layout_type: Mapped[str] = mapped_column(String(32), default="Detail")
    sections: Mapped[list] = mapped_column(JSONB, default=list)
    related_lists: Mapped[list] = mapped_column(JSONB, default=list)
    mini_layout: Mapped[dict] = mapped_column(JSONB, default=dict)
    quick_actions: Mapped[list] = mapped_column(JSONB, default=list)
    summary_layout: Mapped[dict] = mapped_column(JSONB, default=dict)
    headings: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataProfileModel(Base):
    """Normalized Salesforce Profile storage."""

    __tablename__ = "metadata_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    user_license: Mapped[str] = mapped_column(String(128), default="")
    custom: Mapped[bool] = mapped_column(Boolean, default=False)
    object_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    field_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    class_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    page_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    user_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    record_type_visibilities: Mapped[list] = mapped_column(JSONB, default=list)
    login_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    login_ip_ranges: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataPermissionSetModel(Base):
    """Normalized Salesforce Permission Set storage."""

    __tablename__ = "metadata_permission_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    user_license: Mapped[str] = mapped_column(String(128), default="")
    is_owned_by_profile: Mapped[bool] = mapped_column(Boolean, default=False)
    profile_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    has_activation: Mapped[bool] = mapped_column(Boolean, default=False)
    object_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    field_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    class_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    page_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    user_permissions: Mapped[list] = mapped_column(JSONB, default=list)
    record_type_visibilities: Mapped[list] = mapped_column(JSONB, default=list)
    login_hours: Mapped[dict] = mapped_column(JSONB, default=dict)
    login_ip_ranges: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataReportModel(Base):
    """Normalized Salesforce Report storage."""

    __tablename__ = "metadata_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    folder_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_run_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    columns: Mapped[list] = mapped_column(JSONB, default=list)
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    groupings: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataDashboardModel(Base):
    """Normalized Salesforce Dashboard storage."""

    __tablename__ = "metadata_dashboards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    folder_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    owner_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dashboard_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    components: Mapped[list] = mapped_column(JSONB, default=list)
    filters: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataWorkflowRuleModel(Base):
    """Normalized Salesforce Workflow Rule storage."""

    __tablename__ = "metadata_workflow_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    trigger_type: Mapped[str] = mapped_column(String(64), default="onCreateOrTriggeringUpdate")
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    actions: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataRelationshipModel(Base):
    """Normalized Salesforce Relationship storage."""

    __tablename__ = "metadata_relationships"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    source_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(32), default="lookup")
    cascade_delete: Mapped[bool] = mapped_column(Boolean, default=False)
    junction_object: Mapped[str | None] = mapped_column(String(256), nullable=True)
    field_api_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataDependencyModel(Base):
    """Persistent dependency graph edge storage."""

    __tablename__ = "metadata_dependencies"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    source_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    dependency_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_field: Mapped[str | None] = mapped_column(String(256), nullable=True)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    graph_version: Mapped[str] = mapped_column(String(64), default="1.0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class SearchDocumentModel(Base):
    """Persistent search document storage for full-text search."""

    __tablename__ = "search_documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    component_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    component_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    component_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    object_api_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    extra_metadata: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    search_vector: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataRoleModel(Base):
    """Normalized Salesforce Role storage."""

    __tablename__ = "metadata_roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parent_role: Mapped[str | None] = mapped_column(String(256), nullable=True)
    case_access_level: Mapped[str] = mapped_column(String(32), default="None")
    contact_access_level: Mapped[str] = mapped_column(String(32), default="None")
    opportunity_access_level: Mapped[str] = mapped_column(String(32), default="None")
    account_access_level: Mapped[str] = mapped_column(String(32), default="None")
    may_forecast_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataQueueModel(Base):
    """Normalized Salesforce Queue storage."""

    __tablename__ = "metadata_queues"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    email: Mapped[str | None] = mapped_column(String(256), nullable=True)
    queue_sobjects: Mapped[list] = mapped_column(JSONB, default=list)
    queue_members: Mapped[list] = mapped_column(JSONB, default=list)
    queue_rules: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataPublicGroupModel(Base):
    """Normalized Salesforce Public Group storage."""

    __tablename__ = "metadata_public_groups"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    members: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataSharingRuleModel(Base):
    """Normalized Salesforce Sharing Rule storage."""

    __tablename__ = "metadata_sharing_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    shared_to: Mapped[str] = mapped_column(String(256), default="")
    shared_from: Mapped[str] = mapped_column(String(256), default="")
    access_level: Mapped[str] = mapped_column(String(32), default="Read")
    rule_type: Mapped[str] = mapped_column(String(64), default="CriteriaBased")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataGlobalValueSetModel(Base):
    """Normalized Salesforce Global Value Set storage."""

    __tablename__ = "metadata_global_value_sets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    master_label: Mapped[str] = mapped_column(String(256), default="")
    custom_value: Mapped[list] = mapped_column(JSONB, default=list)
    grouped: Mapped[bool] = mapped_column(Boolean, default=False)
    sorting_order: Mapped[str] = mapped_column(String(32), default="Alphabetical")
    value_settings: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataCustomMetadataModel(Base):
    """Normalized Salesforce Custom Metadata Type storage."""

    __tablename__ = "metadata_custom_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    visibility: Mapped[str] = mapped_column(String(32), default="Public")
    fields: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataCustomSettingModel(Base):
    """Normalized Salesforce Custom Setting storage."""

    __tablename__ = "metadata_custom_settings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    setting_type: Mapped[str] = mapped_column(String(32), default="list")
    visibility: Mapped[str] = mapped_column(String(32), default="Public")
    fields: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataFlowVersionModel(Base):
    """Normalized Salesforce Flow Version storage."""

    __tablename__ = "metadata_flow_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    flow_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    definition: Mapped[dict] = mapped_column(JSONB, default=dict)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataEmailTemplateModel(Base):
    """Normalized Salesforce Email Template storage."""

    __tablename__ = "metadata_email_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    template_type: Mapped[str] = mapped_column(String(32), default="text")
    object_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    content: Mapped[str] = mapped_column(Text, default="")
    subject: Mapped[str] = mapped_column(Text, default="")
    encoding: Mapped[str] = mapped_column(String(32), default="UTF-8")
    style: Mapped[str] = mapped_column(String(32), default="none")
    ui_type: Mapped[str] = mapped_column(String(32), default="Aloha")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataNamedCredentialModel(Base):
    """Normalized Salesforce Named Credential storage."""

    __tablename__ = "metadata_named_credentials"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    endpoint: Mapped[str] = mapped_column(String(512), default="")
    principal_type: Mapped[str] = mapped_column(String(32), default="Anonymous")
    protocol: Mapped[str] = mapped_column(String(32), default="NoAuthentication")
    auth_provider: Mapped[str | None] = mapped_column(String(256), nullable=True)
    generate_authorization_header: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_merge_fields_in_header: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_merge_fields_in_body: Mapped[bool] = mapped_column(Boolean, default=True)
    outbound_network_connection: Mapped[str | None] = mapped_column(String(256), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataConnectedAppModel(Base):
    """Normalized Salesforce Connected App storage."""

    __tablename__ = "metadata_connected_apps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    contact_email: Mapped[str] = mapped_column(String(256), default="")
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    info_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mobile_app: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mobile_start_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    oauth_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    permissions: Mapped[list] = mapped_column(JSONB, default=list)
    permissions_enabled: Mapped[list] = mapped_column(JSONB, default=list)
    plugin: Mapped[str | None] = mapped_column(String(256), nullable=True)
    plugin_execution_user: Mapped[str | None] = mapped_column(String(256), nullable=True)
    start_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataLightningPageModel(Base):
    """Normalized Salesforce Lightning Page storage."""

    __tablename__ = "metadata_lightning_pages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    master_label: Mapped[str] = mapped_column(String(256), default="")
    page_type: Mapped[str] = mapped_column(String(64), default="RecordPage")
    template: Mapped[str | None] = mapped_column(String(256), nullable=True)
    regions: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataQuickActionModel(Base):
    """Normalized Salesforce Quick Action storage."""

    __tablename__ = "metadata_quick_actions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), default="Create")
    target_object: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_record_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_field_list: Mapped[str | None] = mapped_column(String(256), nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icon: Mapped[str | None] = mapped_column(String(256), nullable=True)
    options_create: Mapped[bool] = mapped_column(Boolean, default=True)
    options_edit: Mapped[bool] = mapped_column(Boolean, default=True)
    options_event: Mapped[bool] = mapped_column(Boolean, default=False)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataFormulaModel(Base):
    """Normalized Salesforce Formula storage."""

    __tablename__ = "metadata_formulas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    field_api_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    formula_expression: Mapped[str] = mapped_column(Text, default="")
    formula_type: Mapped[str] = mapped_column(String(32), default="formula")
    formula_treat_blanks_as: Mapped[str] = mapped_column(String(32), default="BlankAsBlank")
    return_type: Mapped[str] = mapped_column(String(32), default="Text")
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )


class MetadataApprovalProcessModel(Base):
    """Normalized Salesforce Approval Process storage."""

    __tablename__ = "metadata_approval_processes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True,
    )
    object_api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    api_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    record_editability: Mapped[str] = mapped_column(String(32), default="Editable")
    allow_sequential: Mapped[bool] = mapped_column(Boolean, default=True)
    show_approval_related_lists: Mapped[bool] = mapped_column(Boolean, default=True)
    entry_criteria: Mapped[str] = mapped_column(Text, default="")
    final_approval_field_lookup: Mapped[str | None] = mapped_column(String(256), nullable=True)
    final_rejection_field_lookup: Mapped[str | None] = mapped_column(String(256), nullable=True)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    metadata_properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now, onupdate=datetime.now, nullable=False,
    )
