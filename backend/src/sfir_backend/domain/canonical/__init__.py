from sfir_backend.domain.canonical.access import (
    MetadataPublicGroup,
    MetadataQueue,
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    ComponentVisibility,
    FieldType,
    LayoutType,
    MetadataComponent,
    MetadataStatus,
    RelationshipType,
    SourcePlatform,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import (
    MetadataField,
    MetadataGlobalValueSet,
    MetadataObject,
    MetadataRelationship,
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

__all__ = [
    "CanonicalRelationship",
    "ComponentVisibility",
    "FieldType",
    "LayoutType",
    "MetadataApexClass",
    "MetadataApprovalProcess",
    "MetadataComponent",
    "MetadataConnectedApp",
    "MetadataCustomMetadata",
    "MetadataCustomSetting",
    "MetadataDashboard",
    "MetadataEmailTemplate",
    "MetadataField",
    "MetadataFlow",
    "MetadataFlowVersion",
    "MetadataFormula",
    "MetadataGlobalValueSet",
    "MetadataLayout",
    "MetadataLightningPage",
    "MetadataNamedCredential",
    "MetadataObject",
    "MetadataPermissionSet",
    "MetadataProfile",
    "MetadataPublicGroup",
    "MetadataQueue",
    "MetadataQuickAction",
    "MetadataRecordType",
    "MetadataRelationship",
    "MetadataReport",
    "MetadataRole",
    "MetadataSharingRule",
    "MetadataStatus",
    "MetadataTrigger",
    "MetadataValidationRule",
    "MetadataWorkflow",
    "RelationshipType",
    "SourcePlatform",
]
