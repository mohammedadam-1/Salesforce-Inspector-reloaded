"""CanonicalRelationshipResolver.

Resolves the typed, directional relationships between canonical metadata
components (or their normalized dict form). The resolver is PURE: it never
reads the store, never traverses, never computes impact — it only derives
edges from the given components and the known/deleted target identity sets
provided by the caller, and returns persistable relationship rows.

Reference targets that are neither known nor deleted are counted as
missing references and dropped. Targets whose canonical document is
soft-deleted produce relationship rows marked deleted. Invocable-action
targets are treated as external references (no component type exists in
the canonical store) and are always kept.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sfir_backend.application.pipeline.normalizer.identity_service import (
    IdentityService,
)
from sfir_backend.domain.canonical.base import MetadataComponent, MetadataStatus
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationship,
    CanonicalRelationshipType,
)

# Target types that never resolve to a canonical document component and are
# therefore exempt from known/deleted filtering (external references).
EXTERNAL_TARGET_TYPES = frozenset({"invocable_action"})

_FORMULA_BRACKET_RE = re.compile(r"\[([^\]]+)\]")
_FORMULA_SETUP_OBJECT_RE = re.compile(r"\$Setup\.([A-Za-z0-9_]+)")
_FORMULA_OBJECT_TYPE_RE = re.compile(r"\$ObjectType\.([A-Za-z0-9_]+)")
_APEX_USAGE_RE = re.compile(
    r"\bnew\s+([A-Z][A-Za-z0-9_]*)\b"
    r"|\b([A-Z][A-Za-z0-9_]*)\.\s*(?![A-Za-z0-9_]*\.)",
)

_OBJECT_CHILD_NAMES = ("name", "fullName", "api_name", "apiName")


@dataclass
class RelationshipResolutionResult:
    relationships: list[CanonicalRelationship] = field(default_factory=list)
    missing_references: int = 0
    errors: list[str] = field(default_factory=list)


class _View:
    """Uniform read adapter over a MetadataComponent or a normalized dict."""

    def __init__(self, item: Any) -> None:
        self._item = item
        self.is_component = isinstance(item, MetadataComponent)

    @property
    def identity(self) -> str:
        if self.is_component:
            return str(self._item.id) if getattr(self._item, "id", None) else ""
        return str(self._item.get("identity", ""))

    @property
    def type(self) -> str:
        if self.is_component:
            return str(getattr(self._item, "type", ""))
        return str(self._item.get("type", "")).lower()

    @property
    def api_name(self) -> str:
        if self.is_component:
            return str(getattr(self._item, "api_name", "") or "")
        return str(self._item.get("api_name", "") or "")

    @property
    def namespace(self) -> str | None:
        if self.is_component:
            return getattr(self._item, "namespace", None)
        return self._item.get("namespace")

    @property
    def is_deleted(self) -> bool:
        if self.is_component:
            return getattr(self._item, "status", None) == MetadataStatus.DELETED
        return bool(self._item.get("deleted", False)) or self._item.get("status") == "deleted"

    @property
    def object_api_name(self) -> str:
        return str(self.get("object_api_name") or "")

    def get(self, name: str, default: Any = None) -> Any:
        if self.is_component:
            value = getattr(self._item, name, None)
            if value is None:
                props = getattr(self._item, "metadata_properties", None) or {}
                value = props.get(name)
            return value if value is not None else default
        value = self._item.get(name)
        if value is None:
            props = self._item.get("properties") or {}
            value = props.get(name)
        if value is None:
            raw = self._item.get("raw_source") or {}
            value = raw.get(name)
        return value if value is not None else default


class CanonicalRelationshipResolver:
    def __init__(self, identity_service: IdentityService | None = None) -> None:
        self._identity_service = identity_service or IdentityService()

    def resolve(
        self,
        org_id: str,
        components: list[Any],
        *,
        active_targets: set[str] | None = None,
        deleted_targets: set[str] | None = None,
        sync_job_id: Any = None,
    ) -> RelationshipResolutionResult:
        """Resolve relationships for a batch of components.

        ``active_targets`` and ``deleted_targets`` are the identity sets of
        canonical documents currently active / soft-deleted; both should
        include the batch's own identities for a self-contained batch.
        """
        result = RelationshipResolutionResult()
        active = active_targets or set()
        deleted = deleted_targets or set()
        raw_edges: list[tuple] = []

        for item in components:
            view = _View(item)
            if not view.identity or not view.type:
                continue
            try:
                raw_edges.extend(self._extract(view))
            except Exception as exc:  # pragma: no cover - defensive
                result.errors.append(f"relationship resolution failed for {view.api_name}: {exc}")

        seen: set[tuple[str, str, str]] = set()
        for edge in raw_edges:
            (
                source_identity,
                source_api_name,
                source_type,
                source_deleted,
                rel_type,
                target_type,
                target_api,
                target_ns,
            ) = edge
            target_identity = self._identity_service.compute_component_hash(
                organization_id=str(org_id),
                source_platform="salesforce",
                type_name=target_type,
                api_name=target_api,
                namespace=target_ns,
            )
            key = (source_identity, target_identity, rel_type.value)
            if key in seen:
                continue
            seen.add(key)

            deleted_edge = source_deleted
            if target_type in EXTERNAL_TARGET_TYPES or target_identity in active:
                pass
            elif target_identity in deleted:
                deleted_edge = True
            else:
                result.missing_references += 1
                continue

            rel = CanonicalRelationship.create(
                organization_id=org_id,
                source_identity=source_identity,
                source_api_name=source_api_name,
                source_type=source_type,
                target_identity=target_identity,
                target_api_name=target_api,
                target_type=target_type,
                relationship_type=rel_type,
                sync_job_id=sync_job_id,
            )
            if deleted_edge:
                rel.soft_delete(sync_job_id=sync_job_id)
            result.relationships.append(rel)
        return result

    # ------------------------------------------------------------------
    # Extraction — one branch per relationship kind
    # ------------------------------------------------------------------

    def _extract(
        self,
        view: _View,
    ) -> list[tuple]:
        kind = view.type
        edges: list[tuple] = []

        if kind == "object":
            self._extract_object_containment(view, edges)
        elif kind == "field":
            self._extract_field(view, edges)
        elif kind == "trigger":
            self._extract_trigger(view, edges)
        elif kind == "layout":
            self._extract_layout(view, edges)
        elif kind == "record_type":
            self._extract_record_type(view, edges)
        elif kind == "validation_rule":
            self._extract_validation_rule(view, edges)
        elif kind == "flow":
            self._extract_flow(view, edges)
        elif kind == "permission_set":
            self._extract_permission_set(view, edges)
        elif kind == "custom_metadata":
            self._extract_custom_metadata(view, edges)
        return edges

    def _extract_object_containment(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        for entry in _as_list(view.get("fields")):
            name = _entry_name(entry)
            if not name:
                continue
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_FIELD,
                "field", _compound(view.api_name, name),
            ))
        for entry in _as_list(view.get("record_types")):
            name = _entry_name(entry)
            if not name:
                continue
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_RECORD_TYPE,
                "record_type", _compound(view.api_name, name),
            ))
        for entry in _as_list(view.get("validation_rules")):
            name = _entry_name(entry)
            if not name:
                continue
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_VALIDATION_RULE,
                "validation_rule", _compound(view.api_name, name),
            ))

    def _extract_field(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        parent_name = view.object_api_name or _parent_object_api(view)
        if parent_name:
            edges.append(self._edge(
                view, CanonicalRelationshipType.FIELD_TO_OBJECT, "object", parent_name,
            ))
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_FIELD, "field", view.api_name,
            ))

        reference_to = view.get("reference_to")
        if reference_to:
            edges.append(self._edge(
                view, CanonicalRelationshipType.FIELD_TO_LOOKUP_TARGET, "object", str(reference_to),
            ))

        formula = view.get("formula")
        if formula:
            for target_name in _FORMULA_BRACKET_RE.findall(str(formula)):
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE,
                    "field", target_name,
                ))
            for target_name in _FORMULA_SETUP_OBJECT_RE.findall(str(formula)):
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE,
                    "object", target_name,
                ))
            for target_name in _FORMULA_OBJECT_TYPE_RE.findall(str(formula)):
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FIELD_TO_FORMULA_REFERENCE,
                    "object", target_name,
                ))

    def _extract_trigger(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        parent_name = view.object_api_name or _parent_object_api(view)
        if parent_name:
            edges.append(self._edge(
                view, CanonicalRelationshipType.TRIGGER_TO_OBJECT, "object", parent_name,
            ))
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_TRIGGER, "trigger", view.api_name,
            ))
        body = view.get("body")
        if body:
            for name in _APEX_USAGE_RE.findall(str(body)):
                class_name = name[0] or name[1]
                if class_name:
                    edges.append(self._edge(
                        view, CanonicalRelationshipType.TRIGGER_TO_APEX, "apex_class", class_name,
                    ))

    def _extract_layout(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        parent_name = view.object_api_name or _parent_object_api(view)
        if parent_name:
            edges.append(self._edge(
                view, CanonicalRelationshipType.LAYOUT_TO_OBJECT, "object", parent_name,
            ))
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_LAYOUT, "layout", view.api_name,
            ))

    def _extract_record_type(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        parent_name = view.object_api_name or _parent_object_api(view)
        if parent_name:
            edges.append(self._edge(
                view, CanonicalRelationshipType.RECORD_TYPE_TO_OBJECT, "object", parent_name,
            ))
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_RECORD_TYPE, "record_type", view.api_name,
            ))

    def _extract_validation_rule(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        parent_name = view.object_api_name or _parent_object_api(view)
        if parent_name:
            edges.append(self._edge(
                view, CanonicalRelationshipType.OBJECT_TO_VALIDATION_RULE,
                "validation_rule", view.api_name,
            ))

    def _extract_flow(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        for obj_key in ("record_creates", "record_updates", "record_deletes"):
            for obj_name in _string_list(view.get(obj_key)):
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FLOW_TO_OBJECT, "object", obj_name,
                ))
        for flow_name in _string_list(view.get("subflows")):
            edges.append(self._edge(
                view, CanonicalRelationshipType.FLOW_TO_FLOW, "flow", flow_name,
            ))
        for element in _as_list(view.get("elements")):
            element_type = str(element.get("element_type") or element.get("type") or "").lower()
            element_name = str(
                element.get("action_name")
                or element.get("actionName")
                or element.get("name")
                or "",
            )
            if not element_name:
                continue
            if "apex" in element_type:
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FLOW_TO_APEX, "apex_class", element_name,
                ))
            elif "subflow" in element_type:
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FLOW_TO_FLOW, "flow", element_name,
                ))
            elif element_type in (
                "action", "action_call", "actioncall", "invocable", "invocable_action",
            ):
                edges.append(self._edge(
                    view, CanonicalRelationshipType.FLOW_TO_INVOCABLE_ACTION,
                    "invocable_action", element_name,
                ))

    def _extract_permission_set(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        for op in _as_list(view.get("object_permissions")):
            obj_name = str(op.get("object") or op.get("name") or "")
            if obj_name:
                edges.append(self._edge(
                    view, CanonicalRelationshipType.PERMISSION_SET_TO_OBJECT, "object", obj_name,
                ))
        for fp in _as_list(view.get("field_permissions")):
            field_name = str(fp.get("field") or fp.get("name") or "")
            if field_name:
                edges.append(self._edge(
                    view, CanonicalRelationshipType.PERMISSION_SET_TO_FIELD, "field", field_name,
                ))
        profile_name = view.get("profile_name")
        if profile_name:
            org_id = (
                str(view._item.organization_id)
                if view.is_component
                else str(view._item.get("organization_id", ""))
            )
            profile_identity = self._identity_service.compute_component_hash(
                organization_id=org_id,
                source_platform="salesforce",
                type_name="profile",
                api_name=str(profile_name),
                namespace=view.namespace,
            )
            edges.append((
                profile_identity, str(profile_name), "profile", False,
                CanonicalRelationshipType.PROFILE_TO_PERMISSION_SET,
                "permission_set", view.api_name, view.namespace,
            ))

    def _extract_custom_metadata(
        self,
        view: _View,
        edges: list[tuple],
    ) -> None:
        for entry in _as_list(view.get("fields")):
            field_type = str(entry.get("type") or "").lower()
            if field_type not in ("reference", "lookup", "master_detail"):
                continue
            value = str(entry.get("value") or entry.get("name") or "")
            if value:
                edges.append(self._edge(
                    view, CanonicalRelationshipType.CUSTOM_METADATA_TO_REFERENCE,
                    "custom_metadata", value,
                ))

    def _edge(
        self,
        view: _View,
        rel_type: CanonicalRelationshipType,
        target_type: str,
        target_api: str,
    ) -> tuple:
        return (
            view.identity, view.api_name, view.type, view.is_deleted,
            rel_type, target_type, target_api, view.namespace,
        )


def _as_list(value: Any) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _string_list(value: Any) -> list[str]:
    return [str(v) for v in _as_list(value)]


def _entry_name(entry: Any) -> str:
    if isinstance(entry, MetadataComponent):
        return entry.api_name or ""
    if isinstance(entry, dict):
        for key in _OBJECT_CHILD_NAMES:
            if entry.get(key):
                return str(entry[key])
    return ""


def _compound(parent: str, name: str) -> str:
    return name if "." in name else f"{parent}.{name}"


def _parent_object_api(view: _View) -> str:
    if view.is_component:
        api_name = view.api_name
        if "." in api_name:
            return api_name.rsplit(".", 1)[0]
        return ""
    parent_key = view._item.get("parent_key") or {}
    if parent_key.get("type") and str(parent_key.get("type", "")).lower() == "object":
        return str(parent_key.get("api_name", ""))
    api_name = view.api_name
    if "." in api_name:
        return api_name.rsplit(".", 1)[0]
    return ""
