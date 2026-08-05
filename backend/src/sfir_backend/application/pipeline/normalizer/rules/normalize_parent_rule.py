from __future__ import annotations

import structlog

from sfir_backend.application.pipeline.normalizer.i_normalization_rule import (
    INormalizationRule,
)
from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.application.pipeline.normalizer.normalized_model import (
    ComponentKey,
    NormalizedDocument,
)
from sfir_backend.domain.canonical.base import MetadataComponent

logger = structlog.get_logger(__name__)

# Metadata types whose component belongs to a parent object component.
# The value is the attribute (or properties key) holding the parent's
# api name; compound api names like "Account.MyField__c" are the fallback.
_CHILD_TYPES_WITH_OBJECT_PARENT: dict[str, str] = {
    "field": "object_api_name",
    "record_type": "object_api_name",
    "validation_rule": "object_api_name",
    "formula": "object_api_name",
}


class NormalizeParentRule(INormalizationRule):
    """Derive developer_name and parent references for child components.

    Every normalized document exposes its developer name (the local part of
    the api name, without parent/namespace prefixes) and, for child types
    (fields, record types, validation rules, layouts, flow versions,
    triggers, relationships), the stable identity of its parent component.
    Children of components present in the same batch are aggregated into
    ``children_identities`` by the normalizer afterwards.
    """

    def __init__(self, identity_service: IdentityService | None = None) -> None:
        self._identity_service = identity_service or IdentityService()

    def can_handle(self, component: MetadataComponent) -> bool:
        return True

    def normalize(
        self,
        component: MetadataComponent,
        normalized: NormalizedDocument,
    ) -> NormalizedDocument:
        props = dict(component.metadata_properties or {})
        normalized.developer_name = self._derive_developer_name(component, props)

        parent_type, parent_name = self._derive_parent(component, props)
        if parent_type and parent_name:
            platform = component.source_platform.value if hasattr(
                component.source_platform, "value",
            ) else str(component.source_platform)
            normalized.parent_identity = self._identity_service.compute_component_hash(
                organization_id=str(component.organization_id),
                source_platform=platform,
                type_name=parent_type,
                api_name=parent_name,
            )
            normalized.parent_key = ComponentKey(
                type=parent_type, api_name=parent_name,
            )
        return normalized

    @staticmethod
    def _derive_developer_name(
        component: MetadataComponent,
        props: dict,
    ) -> str:
        for key in ("developer_name", "fullName", "DeveloperName"):
            if props.get(key):
                return str(props[key])
        api_name = component.api_name or ""
        local = api_name.rsplit(".", 1)[-1]
        namespace = component.namespace
        if namespace and local.startswith(f"{namespace}__"):
            return local[len(namespace) + 2:]
        return local

    @staticmethod
    def _derive_parent(
        component: MetadataComponent,
        props: dict,
    ) -> tuple[str | None, str | None]:
        ctype = component.type
        api_name = component.api_name or ""
        object_parent = _CHILD_TYPES_WITH_OBJECT_PARENT.get(ctype)
        if object_parent:
            parent_name = (
                getattr(component, object_parent, None)
                or props.get(object_parent)
                or _prefix_of_compound(api_name)
            )
            if parent_name:
                return "object", str(parent_name)
            return None, None

        if ctype == "trigger":
            parent_name = (
                getattr(component, "object_api_name", None)
                or props.get("object_api_name")
                or props.get("sobject_name")
                or props.get("sObjectName")
            )
            if parent_name:
                return "object", str(parent_name)
            return None, None

        if ctype == "flow_version":
            parent_name = (
                getattr(component, "flow_api_name", None)
                or props.get("flow_api_name")
                or _strip_version_suffix(api_name)
            )
            if parent_name:
                return "flow", parent_name
            return None, None

        if ctype == "relationship":
            parent_name = (
                getattr(component, "source_api_name", None)
                or props.get("source_api_name")
            )
            parent_type = (
                getattr(component, "source_type", None)
                or props.get("source_type")
            )
            if parent_name and parent_type:
                return str(parent_type), str(parent_name)
            return None, None

        return None, None


def _prefix_of_compound(api_name: str) -> str | None:
    if "." in api_name:
        return api_name.rsplit(".", 1)[0]
    return None


def _strip_version_suffix(api_name: str) -> str | None:
    if not api_name:
        return None
    if "-" in api_name:
        return api_name.rsplit("-", 1)[0]
    return api_name
