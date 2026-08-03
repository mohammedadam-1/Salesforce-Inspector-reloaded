"""SQLAlchemy implementation of the Metadata Repository."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy import Select, delete, select, func, or_, and_, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sfir_backend.domain.canonical.access import (
    MetadataPublicGroup,
    MetadataQueue,
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import (
    MetadataField,
    MetadataGlobalValueSet,
    MetadataObject,
)
from sfir_backend.domain.canonical.custom import (
    MetadataCustomMetadata,
    MetadataCustomSetting,
)
from sfir_backend.domain.canonical.flows import MetadataFlow, MetadataFlowVersion
from sfir_backend.domain.canonical.integration import (
    MetadataConnectedApp,
    MetadataEmailTemplate,
    MetadataNamedCredential,
)
from sfir_backend.domain.canonical.layouts import MetadataLayout, MetadataRecordType
from sfir_backend.domain.canonical.permissions import (
    MetadataPermissionSet,
    MetadataProfile,
)
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.canonical.ui import MetadataLightningPage, MetadataQuickAction
from sfir_backend.domain.canonical.validation import (
    MetadataFormula,
    MetadataValidationRule,
)
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)
from sfir_backend.domain.entities.metadata_sync import MetadataVersion
from sfir_backend.domain.repositories.metadata_repo import (
    IMetadataRepository,
    MetadataFilter,
    Pagination,
    SortOrder,
)
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.domain.value_objects.metadata import MetadataAction
from sfir_backend.infrastructure.persistence.models.metadata_components import (
    MetadataApexClassModel,
    MetadataApprovalProcessModel,
    MetadataConnectedAppModel,
    MetadataCustomMetadataModel,
    MetadataCustomSettingModel,
    MetadataDashboardModel,
    MetadataDependencyModel,
    MetadataEmailTemplateModel,
    MetadataFieldModel,
    MetadataFlowModel,
    MetadataFlowVersionModel,
    MetadataFormulaModel,
    MetadataGlobalValueSetModel,
    MetadataLayoutModel,
    MetadataLightningPageModel,
    MetadataNamedCredentialModel,
    MetadataObjectModel,
    MetadataPermissionSetModel,
    MetadataProfileModel,
    MetadataPublicGroupModel,
    MetadataQueueModel,
    MetadataQuickActionModel,
    MetadataRecordTypeModel,
    MetadataRelationshipModel,
    MetadataReportModel,
    MetadataRoleModel,
    MetadataSharingRuleModel,
    MetadataTriggerModel,
    MetadataValidationRuleModel,
    MetadataWorkflowRuleModel,
    SearchDocumentModel,
)
from sfir_backend.infrastructure.persistence.models.metadata_sync import (
    MetadataVersionModel,
)

logger = structlog.get_logger(__name__)

# Mapping from metadata type string to ORM model class.
# Keys are the canonical PascalCase names produced by the pipeline normalizer
# (e.g. "ApexClass", "Object", "Trigger", "Workflow").  Salesforce API type
# names and canonical snake_case names are resolved via _TYPE_ALIASES below.
_TYPE_TO_ORM_MODEL: dict[str, type] = {
    "ApexClass": MetadataApexClassModel,
    "Trigger": MetadataTriggerModel,
    "Object": MetadataObjectModel,
    "Field": MetadataFieldModel,
    "ValidationRule": MetadataValidationRuleModel,
    "RecordType": MetadataRecordTypeModel,
    "Flow": MetadataFlowModel,
    "FlowVersion": MetadataFlowVersionModel,
    "Layout": MetadataLayoutModel,
    "Profile": MetadataProfileModel,
    "PermissionSet": MetadataPermissionSetModel,
    "Report": MetadataReportModel,
    "Dashboard": MetadataDashboardModel,
    "Workflow": MetadataWorkflowRuleModel,
    "Role": MetadataRoleModel,
    "Queue": MetadataQueueModel,
    "PublicGroup": MetadataPublicGroupModel,
    "SharingRule": MetadataSharingRuleModel,
    "GlobalValueSet": MetadataGlobalValueSetModel,
    "Relationship": MetadataRelationshipModel,
    "CustomMetadata": MetadataCustomMetadataModel,
    "CustomSetting": MetadataCustomSettingModel,
    "EmailTemplate": MetadataEmailTemplateModel,
    "NamedCredential": MetadataNamedCredentialModel,
    "ConnectedApp": MetadataConnectedAppModel,
    "LightningPage": MetadataLightningPageModel,
    "QuickAction": MetadataQuickActionModel,
    "Formula": MetadataFormulaModel,
    "ApprovalProcess": MetadataApprovalProcessModel,
}

# Aliases: canonical snake_case names and Salesforce API type names
# resolve to the canonical PascalCase keys used by _TYPE_TO_ORM_MODEL.
_TYPE_ALIASES: dict[str, str] = {
    "apex_class": "ApexClass",
    "trigger": "Trigger",
    "object": "Object",
    "field": "Field",
    "validation_rule": "ValidationRule",
    "record_type": "RecordType",
    "flow": "Flow",
    "flow_version": "FlowVersion",
    "layout": "Layout",
    "profile": "Profile",
    "permission_set": "PermissionSet",
    "report": "Report",
    "dashboard": "Dashboard",
    "workflow": "Workflow",
    "role": "Role",
    "queue": "Queue",
    "public_group": "PublicGroup",
    "sharing_rule": "SharingRule",
    "global_value_set": "GlobalValueSet",
    "relationship": "Relationship",
    "custom_metadata": "CustomMetadata",
    "custom_setting": "CustomSetting",
    "email_template": "EmailTemplate",
    "named_credential": "NamedCredential",
    "connected_app": "ConnectedApp",
    "lightning_page": "LightningPage",
    "quick_action": "QuickAction",
    "formula": "Formula",
    "approval_process": "ApprovalProcess",
    # Salesforce API type names
    "CustomObject": "Object",
    "CustomField": "Field",
    "ApexTrigger": "Trigger",
    "WorkflowRule": "Workflow",
}


def _resolve_type(raw: str) -> str:
    """Resolve any supported type spelling to its canonical PascalCase name."""
    if raw in _TYPE_TO_ORM_MODEL:
        return raw
    return _TYPE_ALIASES.get(raw, raw)


def _resolve_model(raw: str) -> type | None:
    """Return the ORM model for a type spelling, or None if unsupported."""
    return _TYPE_TO_ORM_MODEL.get(_resolve_type(raw))


# Reverse mapping: ORM model class to canonical metadata type string
_ORM_MODEL_TO_TYPE: dict[type, str] = {v: k for k, v in _TYPE_TO_ORM_MODEL.items()}

# Mapping from canonical PascalCase metadata type to the typed canonical
# domain model used on the read path.  Relationship is an edge, not a
# persisted entity, so it intentionally falls back to the base component.
_TYPE_TO_CANONICAL_CLASS: dict[str, type] = {
    "ApexClass": MetadataApexClass,
    "Trigger": MetadataTrigger,
    "Object": MetadataObject,
    "Field": MetadataField,
    "ValidationRule": MetadataValidationRule,
    "RecordType": MetadataRecordType,
    "Flow": MetadataFlow,
    "FlowVersion": MetadataFlowVersion,
    "Layout": MetadataLayout,
    "Profile": MetadataProfile,
    "PermissionSet": MetadataPermissionSet,
    "Report": MetadataReport,
    "Dashboard": MetadataDashboard,
    "Workflow": MetadataWorkflow,
    "Role": MetadataRole,
    "Queue": MetadataQueue,
    "PublicGroup": MetadataPublicGroup,
    "SharingRule": MetadataSharingRule,
    "GlobalValueSet": MetadataGlobalValueSet,
    "CustomMetadata": MetadataCustomMetadata,
    "CustomSetting": MetadataCustomSetting,
    "EmailTemplate": MetadataEmailTemplate,
    "NamedCredential": MetadataNamedCredential,
    "ConnectedApp": MetadataConnectedApp,
    "LightningPage": MetadataLightningPage,
    "QuickAction": MetadataQuickAction,
    "Formula": MetadataFormula,
    "ApprovalProcess": MetadataApprovalProcess,
}

# Reserved metadata_properties keys used to persist data that has no dedicated
# column so the read path can restore it exactly (lossless round-trip).
_RESERVED_TYPED = "__type_specific__"
_RESERVED_RELATIONSHIPS = "__relationships__"

# Canonical base fields that are persisted through dedicated columns (or the
# repository-managed identity), never through the reserved type-specific stash.
_EXCLUDED_STASH_FIELDS = frozenset({
    "id",
    "organization_id",
    "type",
    "api_name",
    "label",
    "hash",
    "metadata_properties",
    "relationships",
    "created_at",
    "updated_at",
})

# Type-specific column -> canonical field mapping used by _component_to_orm.
# Keys are canonical PascalCase type names; values map ORM column names to
# attributes on the canonical MetadataComponent (or nested in metadata_properties).
_TYPE_SPECIFIC_FIELDS: dict[str, dict[str, str]] = {
    "Object": {
        "plural_label": "plural_label",
        "sharing_model": "sharing_model",
        "deployment_status": "deployment_status",
        "enable_feeds": "enable_feeds",
        "enable_history": "enable_history",
        "enable_reports": "enable_reports",
        "enable_search": "enable_search",
        "enable_sharing": "enable_sharing",
        "enable_bulk_api": "enable_bulk_api",
        "enable_streaming_api": "enable_streaming_api",
        "enable_enhanced_lookup": "enable_enhanced_lookup",
        "is_custom": "is_custom",
        "is_deprecated_and_hidden": "is_deprecated_and_hidden",
        "key_prefix": "key_prefix",
        "created_date": "created_date",
        "last_modified_date": "last_modified_date",
    },
    "Field": {
        "object_api_name": "object_api_name",
        "field_type": "field_type",
        "length": "length",
        "precision": "precision",
        "scale": "scale",
        "required": "required",
        "unique": "unique",
        "external_id": "external_id",
        "default_value": "default_value",
        "picklist_values": "picklist_values",
        "relationship_name": "relationship_name",
        "reference_to": "reference_to",
        "cascade_delete": "cascade_delete",
        "formula": "formula",
        "formula_treat_blanks_as": "formula_treat_blanks_as",
        "help_text": "help_text",
        "business_owner_group": "business_owner_group",
        "business_owner_user": "business_owner_user",
        "compliance": "compliance",
        "tracked_history": "tracked_history",
        "is_custom": "is_custom",
        "is_deprecated_and_hidden": "is_deprecated_and_hidden",
    },
    "ValidationRule": {
        "object_api_name": "object_api_name",
        "active": "active",
        "error_message": "error_message",
        "error_display_field": "error_display_field",
        "formula": "formula",
    },
    "RecordType": {
        "object_api_name": "object_api_name",
        "active": "active",
        "business_process": "business_process",
        "compact_layout_assignment": "compact_layout_assignment",
        "picklist_values": "picklist_values",
    },
    "ApexClass": {
        "api_version": "api_version",
        "body": "body",
        "body_length": "length",
        "package_versions": "package_versions",
        "urls": "urls",
        "is_valid": "is_valid",
        "status": "status",
    },
    "Trigger": {
        "object_api_name": "object_api_name",
        "api_version": "api_version",
        "body": "body",
        "trigger_events": "trigger_events",
        "usage_after_insert": "usage_after_insert",
        "usage_after_update": "usage_after_update",
        "usage_before_insert": "usage_before_insert",
        "usage_before_update": "usage_before_update",
        "usage_after_delete": "usage_after_delete",
        "usage_before_delete": "usage_before_delete",
        "usage_is_bulk": "usage_is_bulk",
        "usage_is_recursive": "usage_is_recursive",
        "status": "status",
    },
    "Flow": {
        "process_type": "process_type",
        "flow_status": "flow_status",
        "version_number": "version_number",
        "api_version": "api_version",
        "interview_label": "interview_label",
        "run_in_mode": "run_in_mode",
        "variables": "variables",
        "stages": "stages",
        "elements": "elements",
        "record_creates": "record_creates",
        "record_updates": "record_updates",
        "record_deletes": "record_deletes",
        "subflows": "subflows",
    },
    "FlowVersion": {
        "flow_api_name": "flow_api_name",
        "version_number": "version_number",
        "definition": "definition",
    },
    "Layout": {
        "object_api_name": "object_api_name",
        "layout_type": "layout_type",
        "sections": "sections",
        "related_lists": "related_lists",
        "mini_layout": "mini_layout",
        "quick_actions": "quick_actions",
        "summary_layout": "summary_layout",
        "headings": "headings",
    },
    "Profile": {
        "user_license": "user_license",
        "custom": "custom",
        "object_permissions": "object_permissions",
        "field_permissions": "field_permissions",
        "class_permissions": "class_permissions",
        "page_permissions": "page_permissions",
        "user_permissions": "user_permissions",
        "record_type_visibilities": "record_type_visibilities",
        "login_hours": "login_hours",
        "login_ip_ranges": "login_ip_ranges",
    },
    "PermissionSet": {
        "user_license": "user_license",
        "is_owned_by_profile": "is_owned_by_profile",
        "profile_name": "profile_name",
        "has_activation": "has_activation",
        "object_permissions": "object_permissions",
        "field_permissions": "field_permissions",
        "class_permissions": "class_permissions",
        "page_permissions": "page_permissions",
        "user_permissions": "user_permissions",
        "record_type_visibilities": "record_type_visibilities",
        "login_hours": "login_hours",
        "login_ip_ranges": "login_ip_ranges",
    },
    "Report": {
        "report_type": "report_type",
        "folder_name": "folder_name",
        "owner_id": "owner_id",
        "last_run_date": "last_run_date",
        "columns": "columns",
        "filters": "filters",
        "groupings": "groupings",
    },
    "Dashboard": {
        "folder_name": "folder_name",
        "owner_id": "owner_id",
        "dashboard_type": "dashboard_type",
        "components": "components",
        "filters": "filters",
    },
    "Workflow": {
        "object_api_name": "object_api_name",
        "active": "active",
        "formula_criteria": "formula_criteria",
        "trigger_type": "trigger_type",
        "formula": "formula",
        "actions": "actions",
    },
    "Role": {
        "parent_role": "parent_role",
        "case_access_level": "case_access_level",
        "contact_access_level": "contact_access_level",
        "opportunity_access_level": "opportunity_access_level",
        "account_access_level": "account_access_level",
        "may_forecast_manager": "may_forecast_manager",
    },
    "Queue": {
        "email": "email",
        "queue_sobjects": "queue_sobjects",
        "queue_members": "queue_members",
        "queue_rules": "queue_rules",
    },
    "PublicGroup": {
        "members": "members",
    },
    "SharingRule": {
        "object_api_name": "object_api_name",
        "shared_to": "shared_to",
        "shared_from": "shared_from",
        "access_level": "access_level",
        "rule_type": "rule_type",
    },
    "GlobalValueSet": {
        "master_label": "master_label",
        "custom_value": "custom_value",
        "grouped": "grouped",
        "sorting_order": "sorting_order",
        "value_settings": "value_settings",
    },
    "CustomMetadata": {
        "visibility": "visibility",
        "fields": "fields",
    },
    "CustomSetting": {
        "setting_type": "setting_type",
        "visibility": "visibility",
        "fields": "fields",
    },
    "EmailTemplate": {
        "template_type": "template_type",
        "object_type": "object_type",
        "available": "available",
        "content": "content",
        "subject": "subject",
        "encoding": "encoding",
        "style": "style",
        "ui_type": "ui_type",
    },
    "NamedCredential": {
        "endpoint": "endpoint",
        "principal_type": "principal_type",
        "protocol": "protocol",
        "auth_provider": "auth_provider",
        "generate_authorization_header": "generate_authorization_header",
        "allow_merge_fields_in_header": "allow_merge_fields_in_header",
        "allow_merge_fields_in_body": "allow_merge_fields_in_body",
        "outbound_network_connection": "outbound_network_connection",
    },
    "ConnectedApp": {
        "version": "version",
        "contact_email": "contact_email",
        "contact_phone": "contact_phone",
        "icon_url": "icon_url",
        "info_url": "info_url",
        "logo_url": "logo_url",
        "mobile_app": "mobile_app",
        "mobile_start_url": "mobile_start_url",
        "oauth_config": "oauth_config",
        "permissions": "permissions",
        "permissions_enabled": "permissions_enabled",
        "plugin": "plugin",
        "plugin_execution_user": "plugin_execution_user",
        "start_url": "start_url",
    },
    "LightningPage": {
        "master_label": "master_label",
        "page_type": "page_type",
        "template": "template",
        "regions": "regions",
    },
    "QuickAction": {
        "object_api_name": "object_api_name",
        "action_type": "action_type",
        "target_object": "target_object",
        "target_record_type": "target_record_type",
        "target_field_list": "target_field_list",
        "height": "height",
        "width": "width",
        "icon": "icon",
        "options_create": "options_create",
        "options_edit": "options_edit",
        "options_event": "options_event",
    },
    "Formula": {
        "object_api_name": "object_api_name",
        "field_api_name": "field_api_name",
        "formula_expression": "formula_expression",
        "formula_type": "formula_type",
        "formula_treat_blanks_as": "formula_treat_blanks_as",
        "return_type": "return_type",
    },
    "ApprovalProcess": {
        "object_api_name": "object_api_name",
        "active": "active",
        "record_editability": "record_editability",
        "allow_sequential": "allow_sequential",
        "show_approval_related_lists": "show_approval_related_lists",
        "entry_criteria": "entry_criteria",
        "final_approval_field_lookup": "final_approval_field_lookup",
        "final_rejection_field_lookup": "final_rejection_field_lookup",
        "steps": "steps",
    },
}


def _jsonable(value: Any) -> Any:
    """Convert a canonical value into a JSONB-serializable scalar."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, (datetime, uuid.UUID)):
        return value.isoformat()
    return value


def _enum_annotation(annotation: Any) -> type | None:
    """Extract a StrEnum type from a (possibly Optional[...]) annotation."""
    if isinstance(annotation, type) and issubclass(annotation, StrEnum):
        return annotation
    for arg in getattr(annotation, "__args__", ()):
        if isinstance(arg, type) and issubclass(arg, StrEnum):
            return arg
    return None


def _coerce_for_field(canonical_cls: type, attr: str, value: Any) -> Any:
    """Coerce a persisted scalar into the canonical field's declared type.

    StrEnum fields are coerced case-insensitively so legacy column values
    such as ``"Active"`` / ``"Draft"`` (vs. lowercase enum values) survive.
    Unparseable values return None so the read path falls back to the field
    default instead of crashing.
    """
    if value is None:
        return None
    enum_type = _enum_annotation(canonical_cls.model_fields[attr].annotation)
    if enum_type is not None and isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            try:
                return enum_type(value.lower())
            except ValueError:  # pragma: no cover - defensive
                return None
    return value


def _coerce_status(value: Any) -> MetadataStatus | None:
    """Safely parse a persisted status column into a MetadataStatus."""
    if isinstance(value, MetadataStatus):
        return value
    if not isinstance(value, str):
        return None
    try:
        return MetadataStatus(value)
    except ValueError:
        try:
            return MetadataStatus(value.lower())
        except ValueError:  # pragma: no cover - defensive
            return None


def _column_covered_attrs(model_class: type | None, resolved_type: str) -> set[str]:
    """Canonical attribute names that are persisted to real columns."""
    covered: set[str] = set()
    if model_class is None:
        return covered
    for column, attr in _TYPE_SPECIFIC_FIELDS.get(resolved_type, {}).items():
        if hasattr(model_class, column):
            covered.add(attr)
    for base_attr in ("namespace", "description"):
        if hasattr(model_class, base_attr):
            covered.add(base_attr)
    return covered


def _stash_non_column_fields(
    component: MetadataComponent,
    resolved_type: str,
    model_class: type | None,
) -> dict[str, Any]:
    """Serialize canonical attributes that have no backing column.

    These live in a reserved ``metadata_properties`` key so the read path can
    restore them exactly (e.g. ``MetadataObject.fields``, ``version``,
    ``source_platform``, or ``namespace``/``description`` on models whose
    tables lack those columns).

    Only non-None values are stashed so base ``MetadataComponent`` instances
    (which simply do not define the typed fields) round-trip to the typed
    model's defaults instead of being force-set to ``None``.
    """
    canonical_cls = _TYPE_TO_CANONICAL_CLASS.get(resolved_type, MetadataComponent)
    covered = _column_covered_attrs(model_class, resolved_type)
    stash: dict[str, Any] = {}
    for name in canonical_cls.model_fields:
        if name in _EXCLUDED_STASH_FIELDS or name in covered:
            continue
        value = getattr(component, name, None)
        if value is None:
            value = component.metadata_properties.get(name)
        if value is not None:
            stash[name] = _jsonable(value)
    return stash


def _component_to_orm(
    organization_id: uuid.UUID,
    component: MetadataComponent,
    model_class: type | None = None,
) -> dict[str, Any]:
    """Convert a canonical MetadataComponent to ORM column values.

    Schema-aware: only columns that exist on the resolved ORM model are
    emitted, so unsupported fields (e.g. ``namespace`` / ``description`` on
    models that lack those columns) never reach the constructor.  Canonical
    attributes with no backing column are preserved inside the reserved
    ``metadata_properties`` keys so the read path restores them exactly.
    """
    resolved_type = _resolve_type(component.type)
    if model_class is None:
        model_class = _TYPE_TO_ORM_MODEL.get(resolved_type)

    base: dict[str, Any] = {
        "organization_id": organization_id,
        "api_name": component.api_name,
        "label": component.label,
        "fingerprint": component.hash or "",
        "metadata_properties": dict(component.metadata_properties),
        "created_at": component.created_at or datetime.now(),
        "updated_at": component.updated_at or datetime.now(),
    }
    # Schema-aware: only emit namespace/description when the model defines them.
    if model_class is not None and hasattr(model_class, "namespace"):
        base["namespace"] = component.namespace
    if model_class is not None and hasattr(model_class, "description"):
        base["description"] = component.description or ""

    # Merge type-specific columns from the canonical component when present.
    # Field values may live directly on the component or inside metadata_properties
    # (normalized dicts produced by the pipeline put everything in properties).
    field_map = _TYPE_SPECIFIC_FIELDS.get(resolved_type, {})
    for column, attr in field_map.items():
        if model_class is not None and not hasattr(model_class, column):
            continue  # schema-aware: never emit a column the model lacks
        value = getattr(component, attr, None)
        if value is None:
            value = component.metadata_properties.get(attr)
        if value is not None:
            # Enum values (e.g. FieldType, MetadataStatus) -> scalar string.
            if hasattr(value, "value"):
                value = value.value
            base[column] = value

    # Preserve canonical attributes without a column (exact round-trip).
    extra = _stash_non_column_fields(component, resolved_type, model_class)
    if extra:
        base["metadata_properties"] = dict(base["metadata_properties"])
        base["metadata_properties"][_RESERVED_TYPED] = extra
    if component.relationships:
        base["metadata_properties"] = dict(base["metadata_properties"])
        base["metadata_properties"][_RESERVED_RELATIONSHIPS] = [
            rel.model_dump(mode="json") for rel in component.relationships
        ]

    return base


def _orm_to_component(orm_model: Any, metadata_type: str) -> MetadataComponent:
    """Convert an ORM model instance to a canonical MetadataComponent.

    Returns the TYPED canonical subclass for the metadata type and restores
    every persisted attribute (base fields, type-specific columns, the
    reserved type-specific stash, and relationships) so round-trips are
    lossless.  Unknown columns are skipped via ``hasattr`` so bare mocks used
    in unit tests never leak auto-created attributes into the model.
    """
    resolved = _resolve_type(metadata_type)
    canonical_cls = _TYPE_TO_CANONICAL_CLASS.get(resolved, MetadataComponent)
    model_class = _TYPE_TO_ORM_MODEL.get(resolved)

    kwargs: dict[str, Any] = {
        "id": str(getattr(orm_model, "id", "") or ""),
        "organization_id": str(getattr(orm_model, "organization_id", "") or ""),
        "type": resolved,
        "api_name": getattr(orm_model, "api_name", ""),
        "label": getattr(orm_model, "label", ""),
        "namespace": getattr(orm_model, "namespace", None),
        "description": getattr(orm_model, "description", None),
        "hash": getattr(orm_model, "fingerprint", None),
        "status": MetadataStatus.ACTIVE,
        "source_platform": SourcePlatform.SALESFORCE,
        "metadata_properties": dict(
            getattr(orm_model, "metadata_properties", {}) or {},
        ),
        "created_at": getattr(orm_model, "created_at", None),
        "updated_at": getattr(orm_model, "updated_at", None),
    }

    # Restore type-specific columns that map to canonical attributes.
    field_map = _TYPE_SPECIFIC_FIELDS.get(resolved, {})
    for column, attr in field_map.items():
        if model_class is None or not hasattr(model_class, column):
            continue  # schema-aware: column does not exist for this type
        if not hasattr(type(orm_model), column):
            continue  # bare MagicMock in unit tests: no real column
        if attr not in canonical_cls.model_fields:
            continue  # e.g. ApexClass "is_valid" has no canonical attribute
        value = getattr(orm_model, column)
        if value is None:
            continue
        kwargs[attr] = _coerce_for_field(canonical_cls, attr, value)

    # Base `status` lives on its own column for ApexClass/Trigger; restore it
    # safely (the legacy column default may be "Active").
    if (
        model_class is not None
        and hasattr(model_class, "status")
        and hasattr(type(orm_model), "status")
    ):
        parsed = _coerce_status(getattr(orm_model, "status"))
        if parsed is not None:
            kwargs["status"] = parsed

    # Restore attributes that have no backing column (reserved stash).
    stash = kwargs["metadata_properties"].pop(_RESERVED_TYPED, None)
    if isinstance(stash, dict):
        for attr, value in stash.items():
            if attr in canonical_cls.model_fields:
                kwargs[attr] = _coerce_for_field(canonical_cls, attr, value)

    # Restore relationships (reserved key written by _component_to_orm).
    rels = kwargs["metadata_properties"].pop(_RESERVED_RELATIONSHIPS, None)
    if isinstance(rels, list):
        try:
            kwargs["relationships"] = [
                CanonicalRelationship(**r) for r in rels if isinstance(r, dict)
            ]
        except (TypeError, ValueError):  # pragma: no cover - defensive
            logger.warning(
                "invalid relationship data in metadata_properties",
                metadata_type=resolved,
            )

    try:
        return canonical_cls(**kwargs)
    except Exception as exc:  # pragma: no cover - defensive fallback
        # Never let a single malformed row crash a bulk read.
        logger.warning(
            "falling back to base MetadataComponent for row",
            metadata_type=resolved,
            api_name=kwargs.get("api_name"),
            error=str(exc),
        )
        return MetadataComponent(**kwargs)


def _version_orm_to_entity(model: Any) -> MetadataVersion:
    """Convert a MetadataVersionModel ORM instance to a domain MetadataVersion."""
    return MetadataVersion(
        id=model.id,
        organization_id=model.organization_id,
        sync_job_id=model.sync_job_id,
        component_type=model.component_type,
        component_name=model.component_name,
        component_id=model.component_id,
        hash=model.hash,
        version_number=model.version_number,
        action=MetadataAction(model.action),
        payload=model.payload,
        salesforce_last_modified=model.salesforce_last_modified,
        sync_timestamp=model.sync_timestamp,
        change_source=model.change_source,
        created_at=model.created_at,
    )


def _version_to_orm(version: MetadataVersion) -> MetadataVersionModel:
    """Convert a domain MetadataVersion to a MetadataVersionModel ORM instance."""
    return MetadataVersionModel(
        id=version.id,
        organization_id=version.organization_id,
        sync_job_id=version.sync_job_id,
        component_type=version.component_type,
        component_name=version.component_name,
        component_id=version.component_id,
        hash=version.hash,
        version_number=version.version_number,
        action=version.action.value,
        payload=version.payload,
        salesforce_last_modified=version.salesforce_last_modified,
        sync_timestamp=version.sync_timestamp,
        change_source=version.change_source,
        created_at=version.created_at,
    )


def _build_base_query(
    organization_id: uuid.UUID,
    model_class: type,
    *,
    filter: MetadataFilter | None = None,
    sort: SortOrder | None = None,
    pagination: Pagination | None = None,
) -> Select:
    """Build a base SQLAlchemy query with filtering, sorting, and pagination."""
    query = select(model_class).where(
        model_class.organization_id == organization_id,
    )

    if filter:
        if filter.search_text:
            search = f"%{filter.search_text}%"
            if hasattr(model_class, "api_name") and hasattr(model_class, "label"):
                query = query.where(
                    or_(
                        model_class.api_name.ilike(search),
                        model_class.label.ilike(search),
                    ),
                )
        if filter.namespaces and hasattr(model_class, "namespace"):
            query = query.where(model_class.namespace.in_(filter.namespaces))

    if sort:
        sort_col = getattr(model_class, sort.field, None)
        if sort_col is not None:
            query = query.order_by(
                sort_col.desc() if sort.descending else sort_col.asc(),
            )
    else:
        query = query.order_by(model_class.api_name.asc())

    if pagination:
        query = query.offset(pagination.offset).limit(pagination.limit)

    return query


class SQLAlchemyMetadataRepository(IMetadataRepository):
    """SQLAlchemy-backed metadata repository.

    Maps between canonical MetadataComponent domain models and
    the normalized ORM tables in metadata_components.py.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _verify_tenant(
        self,
        organization_id: uuid.UUID,
        request_context: RequestContext | None = None,
    ) -> None:
        """Verify tenant isolation using RequestContext if provided."""
        if request_context and request_context.is_authenticated:
            ctx_org = request_context.organization_id
            if ctx_org is not None and ctx_org != organization_id:
                raise PermissionError(
                    f"RequestContext org {ctx_org} does not match "
                    f"requested org {organization_id}",
                )

    async def save(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent:
        self._verify_tenant(organization_id, request_context)
        resolved_type = _resolve_type(component.type)
        if resolved_type == "Relationship":
            raise ValueError(
                "Relationship components are edges, not entities; persist them "
                "via the `relationships` list on their source component",
            )
        model_class = _resolve_model(component.type)
        if model_class is None:
            raise ValueError(f"Unsupported metadata type: {component.type}")

        values = _component_to_orm(
            organization_id, component, model_class=model_class,
        )
        instance = model_class(**values)
        self._session.add(instance)
        await self._session.flush()
        if component.relationships:
            await self._replace_relationships(organization_id, component)
            await self._session.flush()
        return _orm_to_component(instance, resolved_type)

    async def save_batch(
        self,
        organization_id: uuid.UUID,
        components: list[MetadataComponent],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        results: list[MetadataComponent] = []
        instances = []
        for component in components:
            if _resolve_type(component.type) == "Relationship":
                raise ValueError(
                    "Relationship components are edges, not entities; persist "
                    "them via the `relationships` list on their source component",
                )
            model_class = _resolve_model(component.type)
            if model_class is None:
                raise ValueError(f"Unsupported metadata type: {component.type}")
            values = _component_to_orm(
                organization_id, component, model_class=model_class,
            )
            instances.append(model_class(**values))
        self._session.add_all(instances)
        # Single flush for the whole batch, not one per component.
        await self._session.flush()
        # Mirror relationship edges for any component that declares them.
        for component in components:
            if component.relationships:
                await self._replace_relationships(organization_id, component)
        if any(c.relationships for c in components):
            await self._session.flush()
        for component, instance in zip(components, instances, strict=False):
            results.append(
                _orm_to_component(instance, _resolve_type(component.type)),
            )
        return results

    async def update(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent:
        self._verify_tenant(organization_id, request_context)
        model_class = _resolve_model(component.type)
        if model_class is None:
            raise ValueError(f"Unsupported metadata type: {component.type}")

        query = select(model_class).where(
            model_class.organization_id == organization_id,
            model_class.api_name == component.api_name,
        )
        result = await self._session.execute(query)
        instance = result.scalar_one_or_none()
        if instance is None:
            raise ValueError(
                f"Component not found: {component.type}/{component.api_name}",
            )

        values = _component_to_orm(
            organization_id, component, model_class=model_class,
        )
        for key, value in values.items():
            if hasattr(instance, key):
                setattr(instance, key, value)

        setattr(instance, "updated_at", datetime.now())
        await self._session.flush()
        if component.relationships:
            await self._replace_relationships(organization_id, component)
            await self._session.flush()
        return _orm_to_component(instance, component.type)

    async def delete(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> bool:
        self._verify_tenant(organization_id, request_context)
        deleted = False
        for model_class in _TYPE_TO_ORM_MODEL.values():
            if hasattr(model_class, "api_name"):
                query = select(model_class).where(
                    model_class.organization_id == organization_id,
                    model_class.api_name == api_name,
                )
                result = await self._session.execute(query)
                instance = result.scalar_one_or_none()
                if instance:
                    await self._session.delete(instance)
                    deleted = True
        if deleted:
            # Clean up relationship edges pointing at the removed component.
            await self._session.execute(
                delete(MetadataRelationshipModel).where(
                    MetadataRelationshipModel.organization_id == organization_id,
                    or_(
                        MetadataRelationshipModel.source_api_name == api_name,
                        MetadataRelationshipModel.target_api_name == api_name,
                    ),
                ),
            )
        await self._session.flush()
        return deleted

    async def _replace_relationships(
        self,
        organization_id: uuid.UUID,
        component: MetadataComponent,
    ) -> None:
        """Replace the persisted relationship edges for a component.

        The canonical ``component.relationships`` list is the source of truth
        for the round-trip (persisted via the reserved metadata_properties
        key); the edge table mirrors the same edges so cross-component
        queries such as ``get_relationships`` become functional.
        """
        await self._session.execute(
            delete(MetadataRelationshipModel).where(
                MetadataRelationshipModel.organization_id == organization_id,
                MetadataRelationshipModel.source_api_name == component.api_name,
            ),
        )
        for rel in component.relationships:
            self._session.add(MetadataRelationshipModel(
                organization_id=organization_id,
                source_api_name=component.api_name,
                source_type=_resolve_type(component.type),
                target_api_name=rel.target_api_name,
                target_type=rel.target_type,
                relationship_type=(
                    rel.type.value if hasattr(rel.type, "value") else str(rel.type)
                ),
                cascade_delete=getattr(rel, "cascade_delete", False),
                junction_object=getattr(rel, "junction_object", None),
                metadata_properties=dict(rel.metadata or {}),
            ))

    async def get_by_id(
        self,
        organization_id: uuid.UUID,
        component_id: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent | None:
        self._verify_tenant(organization_id, request_context)
        try:
            cid = uuid.UUID(component_id) if len(component_id) == 36 else component_id
        except (ValueError, AttributeError):
            cid = component_id

        for metadata_type, model_class in _TYPE_TO_ORM_MODEL.items():
            if hasattr(model_class, "id"):
                query = select(model_class).where(
                    model_class.organization_id == organization_id,
                    model_class.id == cid,
                )
                result = await self._session.execute(query)
                instance = result.scalar_one_or_none()
                if instance:
                    return _orm_to_component(instance, metadata_type)
        return None

    async def get_by_api_name(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataComponent | None:
        self._verify_tenant(organization_id, request_context)
        for metadata_type, model_class in _TYPE_TO_ORM_MODEL.items():
            if hasattr(model_class, "api_name"):
                query = select(model_class).where(
                    model_class.organization_id == organization_id,
                    model_class.api_name == api_name,
                )
                result = await self._session.execute(query)
                instance = result.scalar_one_or_none()
                if instance:
                    return _orm_to_component(instance, metadata_type)
        return None

    async def get_by_api_names(
        self,
        organization_id: uuid.UUID,
        api_names: list[str],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        if not api_names:
            return []

        results: list[MetadataComponent] = []
        # One batched query per ORM table (bounded by the 13 known types),
        # regardless of how many api_names are requested — avoids N+1.
        for metadata_type, model_class in _TYPE_TO_ORM_MODEL.items():
            if not hasattr(model_class, "api_name"):
                continue
            query = select(model_class).where(
                model_class.organization_id == organization_id,
                model_class.api_name.in_(api_names),
            ).order_by(model_class.api_name.asc())
            result = await self._session.execute(query)
            instances = result.scalars().all()
            results.extend(
                _orm_to_component(inst, metadata_type) for inst in instances
            )
        return results

    async def get_versions(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        self._verify_tenant(organization_id, request_context)
        query = select(MetadataVersionModel).where(
            MetadataVersionModel.organization_id == organization_id,
            MetadataVersionModel.component_name == api_name,
        ).order_by(MetadataVersionModel.version_number.desc())
        if pagination:
            query = query.offset(pagination.offset).limit(pagination.limit)
        result = await self._session.execute(query)
        return [_version_orm_to_entity(m) for m in result.scalars().all()]

    async def get_latest_version(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataVersion | None:
        self._verify_tenant(organization_id, request_context)
        query = (
            select(MetadataVersionModel)
            .where(
                MetadataVersionModel.organization_id == organization_id,
                MetadataVersionModel.component_name == api_name,
            )
            .order_by(MetadataVersionModel.version_number.desc())
            .limit(1)
        )
        result = await self._session.execute(query)
        model = result.scalar_one_or_none()
        return _version_orm_to_entity(model) if model else None

    async def list_versions_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        limit: int = 100,
        offset: int = 0,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        """Bulk-load version rows for an organization (change detection).

        Returns versions ordered by version_number ascending so callers can
        cheaply derive per-component latest versions while scanning.
        """
        self._verify_tenant(organization_id, request_context)
        query = (
            select(MetadataVersionModel)
            .where(MetadataVersionModel.organization_id == organization_id)
            .order_by(
                MetadataVersionModel.component_name.asc(),
                MetadataVersionModel.version_number.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(query)
        return [_version_orm_to_entity(m) for m in result.scalars().all()]

    async def save_version(
        self,
        organization_id: uuid.UUID,
        version: MetadataVersion,
        *,
        request_context: RequestContext | None = None,
    ) -> MetadataVersion:
        self._verify_tenant(organization_id, request_context)
        model = _version_to_orm(version)
        self._session.add(model)
        await self._session.flush()
        return _version_orm_to_entity(model)

    async def save_versions(
        self,
        organization_id: uuid.UUID,
        versions: list[MetadataVersion],
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataVersion]:
        """Persist many versions in a single flush (no per-row commit)."""
        self._verify_tenant(organization_id, request_context)
        if not versions:
            return []
        models = [_version_to_orm(v) for v in versions]
        self._session.add_all(models)
        await self._session.flush()
        return [_version_orm_to_entity(m) for m in models]

    async def get_by_type(
        self,
        organization_id: uuid.UUID,
        metadata_type: str,
        *,
        pagination: Pagination | None = None,
        sort: SortOrder | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        resolved_type = _resolve_type(metadata_type)
        model_class = _TYPE_TO_ORM_MODEL.get(resolved_type)
        if model_class is None:
            return []

        query = _build_base_query(
            organization_id, model_class,
            sort=sort, pagination=pagination,
        )
        result = await self._session.execute(query)
        instances = result.scalars().all()
        return [_orm_to_component(inst, resolved_type) for inst in instances]

    async def get_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        filter: MetadataFilter | None = None,
        pagination: Pagination | None = None,
        sort: SortOrder | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        results: list[MetadataComponent] = []

        types_to_query = list(_TYPE_TO_ORM_MODEL.keys())
        if filter and filter.types:
            resolved = {_resolve_type(t) for t in filter.types}
            types_to_query = [t for t in types_to_query if t in resolved]

        for metadata_type in types_to_query:
            model_class = _TYPE_TO_ORM_MODEL[metadata_type]
            if not hasattr(model_class, "api_name"):
                continue
            query = _build_base_query(
                organization_id, model_class,
                filter=filter, sort=sort, pagination=pagination,
            )
            result = await self._session.execute(query)
            instances = result.scalars().all()
            results.extend(
                _orm_to_component(inst, metadata_type) for inst in instances
            )

        return results

    async def get_by_namespace(
        self,
        organization_id: uuid.UUID,
        namespace: str,
        *,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        results: list[MetadataComponent] = []
        for metadata_type, model_class in _TYPE_TO_ORM_MODEL.items():
            if not hasattr(model_class, "namespace"):
                continue
            query = select(model_class).where(
                model_class.organization_id == organization_id,
                model_class.namespace == namespace,
            ).order_by(model_class.api_name.asc())
            if pagination:
                query = query.offset(pagination.offset).limit(pagination.limit)
            result = await self._session.execute(query)
            instances = result.scalars().all()
            results.extend(
                _orm_to_component(inst, metadata_type) for inst in instances
            )
        return results

    async def search(
        self,
        organization_id: uuid.UUID,
        query_text: str,
        *,
        type_filter: list[str] | None = None,
        pagination: Pagination | None = None,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)
        results: list[MetadataComponent] = []

        types_to_query = list(_TYPE_TO_ORM_MODEL.keys())
        if type_filter:
            resolved = {_resolve_type(t) for t in type_filter}
            types_to_query = [t for t in types_to_query if t in resolved]

        search_pattern = f"%{query_text}%"
        for metadata_type in types_to_query:
            model_class = _TYPE_TO_ORM_MODEL[metadata_type]
            if not hasattr(model_class, "api_name") or not hasattr(model_class, "label"):
                continue
            query = select(model_class).where(
                model_class.organization_id == organization_id,
                or_(
                    model_class.api_name.ilike(search_pattern),
                    model_class.label.ilike(search_pattern),
                ),
            ).order_by(model_class.api_name.asc())
            if pagination:
                query = query.offset(pagination.offset).limit(pagination.limit)
            result = await self._session.execute(query)
            instances = result.scalars().all()
            results.extend(
                _orm_to_component(inst, metadata_type) for inst in instances
            )

        return results

    async def get_relationships(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)

        query = select(MetadataRelationshipModel).where(
            MetadataRelationshipModel.organization_id == organization_id,
            or_(
                MetadataRelationshipModel.source_api_name == api_name,
                MetadataRelationshipModel.target_api_name == api_name,
            ),
        )
        result = await self._session.execute(query)
        relationships = result.scalars().all()

        related_names = {
            rel.target_api_name
            if rel.source_api_name == api_name
            else rel.source_api_name
            for rel in relationships
        }
        if not related_names:
            return []

        # Batch-fetch all related components in a bounded set of queries.
        related = await self.get_by_api_names(
            organization_id, sorted(related_names),
            request_context=request_context,
        )
        return [c for c in related if c.api_name in related_names]

    async def get_dependencies(
        self,
        organization_id: uuid.UUID,
        api_name: str,
        *,
        request_context: RequestContext | None = None,
    ) -> list[MetadataComponent]:
        self._verify_tenant(organization_id, request_context)

        query = select(MetadataDependencyModel).where(
            MetadataDependencyModel.organization_id == organization_id,
            or_(
                MetadataDependencyModel.source_api_name == api_name,
                MetadataDependencyModel.target_api_name == api_name,
            ),
        )
        result = await self._session.execute(query)
        dependencies = result.scalars().all()

        dep_names = {
            dep.target_api_name
            if dep.source_api_name == api_name
            else dep.source_api_name
            for dep in dependencies
        }
        if not dep_names:
            return []

        # Batch-fetch all dependent components in a bounded set of queries.
        dep_components = await self.get_by_api_names(
            organization_id, sorted(dep_names),
            request_context=request_context,
        )
        return [c for c in dep_components if c.api_name in dep_names]

    async def count_by_organization(
        self,
        organization_id: uuid.UUID,
        *,
        type_filter: list[str] | None = None,
        request_context: RequestContext | None = None,
    ) -> int:
        self._verify_tenant(organization_id, request_context)
        total = 0
        types_to_query = list(_TYPE_TO_ORM_MODEL.keys())
        if type_filter:
            resolved = {_resolve_type(t) for t in type_filter}
            types_to_query = [t for t in types_to_query if t in resolved]
        for metadata_type in types_to_query:
            model_class = _TYPE_TO_ORM_MODEL[metadata_type]
            query = select(func.count()).select_from(model_class).where(
                model_class.organization_id == organization_id,
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            total += count
        return total

    async def get_types(
        self,
        organization_id: uuid.UUID,
        *,
        request_context: RequestContext | None = None,
    ) -> list[str]:
        self._verify_tenant(organization_id, request_context)
        available_types: list[str] = []
        for metadata_type, model_class in _TYPE_TO_ORM_MODEL.items():
            query = select(func.count()).select_from(model_class).where(
                model_class.organization_id == organization_id,
            )
            result = await self._session.execute(query)
            count = result.scalar_one()
            if count > 0:
                available_types.append(metadata_type)
        return sorted(available_types)
