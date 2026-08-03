"""Deterministic validation rules for the Metadata Validation & Consistency Engine.

Every rule is a pure, deterministic function of the loaded components, the
reference registry, and the optional downloaded counts. Rules never mutate the
input components and never touch the repository — the engine orchestrates all
repository access.

The rules are intentionally conservative: they only read reference data that is
actually present (from ``metadata_properties`` first, then typed attributes).
When reference data is absent for a component type that *requires* it, an
``REFERENCE_DATA_MISSING`` integrity finding is emitted — this is exactly how the
engine surfaces the repository read-path limitation.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Protocol

from sfir_backend.application.pipeline.validator.i_metadata_validator import (
    IMetadataValidator,
)
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    MetadataComponent,
)
from sfir_backend.domain.validation.validation_report import (
    ValidationCategory,
    ValidationFinding,
    ValidationSeverity,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type vocabulary
# ---------------------------------------------------------------------------

# Canonical PascalCase types (repository read path vocabulary).
_PASCAL_TYPES: frozenset[str] = frozenset({
    "ApexClass", "Trigger", "Object", "Field", "Relationship", "GlobalValueSet",
    "ValidationRule", "Formula", "Flow", "FlowVersion", "Layout", "RecordType",
    "Profile", "PermissionSet", "Role", "Queue", "PublicGroup", "SharingRule",
    "EmailTemplate", "NamedCredential", "ConnectedApp", "Report", "Dashboard",
    "LightningPage", "QuickAction", "CustomMetadata", "CustomSetting",
    "Workflow", "ApprovalProcess",
})

_SNAKE_TO_PASCAL: dict[str, str] = {
    "apex_class": "ApexClass",
    "trigger": "Trigger",
    "object": "Object",
    "field": "Field",
    "relationship": "Relationship",
    "global_value_set": "GlobalValueSet",
    "validation_rule": "ValidationRule",
    "formula": "Formula",
    "flow": "Flow",
    "flow_version": "FlowVersion",
    "layout": "Layout",
    "record_type": "RecordType",
    "profile": "Profile",
    "permission_set": "PermissionSet",
    "role": "Role",
    "queue": "Queue",
    "public_group": "PublicGroup",
    "sharing_rule": "SharingRule",
    "email_template": "EmailTemplate",
    "named_credential": "NamedCredential",
    "connected_app": "ConnectedApp",
    "report": "Report",
    "dashboard": "Dashboard",
    "lightning_page": "LightningPage",
    "quick_action": "QuickAction",
    "custom_metadata": "CustomMetadata",
    "custom_setting": "CustomSetting",
    "workflow": "Workflow",
    "approval_process": "ApprovalProcess",
}

_PASCAL_TO_SNAKE: dict[str, str] = {v: k for k, v in _SNAKE_TO_PASCAL.items()}

# Types in the Phase 3.5 validation matrix that have NO ORM table / repository
# representation. They are reported as unsupported rather than silently skipped.
_UNSUPPORTED_TYPES: list[str] = [
    "AuraComponent",
    "LightningWebComponent",
    "ApexPage",
    "ApexComponent",
    "PlatformEvent",
]

# Component types that MUST reference a parent object by api_name.
_OBJECT_REFERENCE_TYPES: dict[str, tuple[str, ...]] = {
    "Field": ("object_api_name",),
    "ValidationRule": ("object_api_name",),
    "Trigger": ("object_api_name",),
    "Formula": ("object_api_name",),
    "Layout": ("object_api_name",),
    "RecordType": ("object_api_name",),
    "Report": ("object_api_name",),
    "Workflow": ("object_api_name",),
    "ApprovalProcess": ("object_api_name",),
    "SharingRule": ("object_api_name",),
    "QuickAction": ("object_api_name",),
    "CustomSetting": ("object_api_name",),
}


def to_pascal_type(raw: str) -> str:
    """Normalize a type name to the canonical PascalCase vocabulary."""
    return _SNAKE_TO_PASCAL.get(raw, raw)


def to_snake_type(raw: str) -> str:
    """Normalize a type name to the snake_case vocabulary."""
    return _PASCAL_TO_SNAKE.get(raw, raw)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _snake_case(name: str) -> str:
    out: list[str] = []
    for ch in name:
        if ch.isupper():
            out.append("_")
            out.append(ch.lower())
        else:
            out.append(ch)
    return "".join(out)


def read_prop(component: MetadataComponent, *aliases: str, default: Any = None) -> Any:
    """Read a type-specific property from a component.

    Resolution order:
      1. ``metadata_properties`` exact key
      2. ``metadata_properties`` camelCase / snake_case / lowercase variant
      3. typed attribute on the component (works for direct-save test fixtures)
    """
    props = component.metadata_properties or {}
    for alias in aliases:
        if alias in props and props[alias] is not None:
            return props[alias]
    for alias in aliases:
        variants = {_camel_case(alias), _snake_case(alias), alias.lower()}
        for variant in variants:
            if variant in props and props[variant] is not None:
                return props[variant]
    for alias in aliases:
        if hasattr(component, alias):
            value = getattr(component, alias)
            if value is not None:
                return value
    return default


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _extract_reference_names(value: Any, keys: tuple[str, ...]) -> list[str]:
    """Extract object/report names from a list of dicts or plain names."""
    names: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            for key in keys:
                if item.get(key):
                    names.append(str(item[key]))
                    break
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def build_reference_registry(
    components: list[MetadataComponent],
) -> dict[str, set[str]]:
    """Index every component by type → set of api_names.

    Also includes a ``*`` key with every api_name across all types, and an
    ``Objects`` alias for readability.
    """
    registry: dict[str, set[str]] = {}
    all_names: set[str] = set()
    for c in components:
        if not c.type or not c.api_name:
            continue
        registry.setdefault(to_pascal_type(c.type), set()).add(c.api_name)
        all_names.add(c.api_name)
    registry["*"] = all_names
    registry["Objects"] = registry.get("Object", set())
    return registry


def _finding(
    category: ValidationCategory,
    severity: ValidationSeverity,
    error_code: str,
    message: str,
    component: MetadataComponent | None = None,
    reference_type: str = "",
    reference_api_name: str = "",
    suggested_action: str = "",
    metadata: dict[str, Any] | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        category=category,
        severity=severity,
        error_code=error_code,
        message=message,
        component_type=component.type if component else "",
        api_name=component.api_name if component else "",
        reference_type=reference_type,
        reference_api_name=reference_api_name,
        suggested_action=suggested_action,
        metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# Rule protocol + registry
# ---------------------------------------------------------------------------


class IValidationRule(Protocol):
    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        ...


class ValidationRuleSet:
    """Ordered collection of deterministic validation rules."""

    def __init__(self) -> None:
        self._rules: list[IValidationRule] = []

    def register(self, rule: IValidationRule) -> None:
        self._rules.append(rule)

    def run(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None = None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for rule in self._rules:
            try:
                findings.extend(
                    rule.validate(
                        components,
                        registry=registry,
                        downloaded_counts=downloaded_counts,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - rules must never crash the run
                logger.exception("validation rule failed: %s", type(rule).__name__)
                findings.append(
                    _finding(
                        ValidationCategory.INTEGRITY,
                        ValidationSeverity.ERROR,
                        "RULE_FAILURE",
                        f"Validation rule {type(rule).__name__} failed: {exc}",
                        suggested_action="Inspect the rule implementation",
                    )
                )
        return findings


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------


class CompletenessRule:
    """Downloaded count == persisted count, per metadata type."""

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        if not downloaded_counts:
            findings.append(
                _finding(
                    ValidationCategory.COMPLETENESS,
                    ValidationSeverity.INFO,
                    "COMPLETENESS_UNVERIFIED",
                    "Downloaded counts were not provided; completeness cannot "
                    "be verified. Pass downloaded_counts or wire sync_job_repo.",
                )
            )
            return findings

        for raw_type, downloaded in downloaded_counts.items():
            canonical = to_pascal_type(raw_type)
            persisted = len(registry.get(canonical, set()))
            if persisted != downloaded:
                findings.append(
                    _finding(
                        ValidationCategory.COMPLETENESS,
                        ValidationSeverity.ERROR,
                        "COUNT_MISMATCH",
                        f"Completeness failure for {canonical}: downloaded="
                        f"{downloaded}, persisted={persisted}",
                        reference_type=canonical,
                        suggested_action=(
                            "Re-run sync for the type or investigate why rows "
                            "are missing from the repository"
                        ),
                        metadata={"downloaded": downloaded, "persisted": persisted},
                    )
                )
        return findings


class DuplicateRule:
    """No duplicate api_names, ids, or canonical keys within the batch."""

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []

        api_name_counts: Counter[tuple[str, str]] = Counter()
        id_counts: Counter[str] = Counter()
        key_counts: Counter[tuple[str, str, str]] = Counter()

        for c in components:
            api_name_counts[(to_pascal_type(c.type), c.api_name)] += 1
            if c.id:
                id_counts[c.id] += 1
            key_counts[(to_pascal_type(c.type), c.api_name, c.namespace or "")] += 1

        for (c_type, api_name), count in api_name_counts.items():
            if count > 1:
                findings.append(
                    _finding(
                        ValidationCategory.DUPLICATE,
                        ValidationSeverity.ERROR,
                        "DUPLICATE_API_NAME",
                        f"Duplicate {c_type} api_name '{api_name}' appears "
                        f"{count} times",
                        reference_type=c_type,
                        reference_api_name=api_name,
                        suggested_action="Remove duplicate rows for the api_name",
                        metadata={"count": count},
                    )
                )

        for c_id, count in id_counts.items():
            if count > 1:
                findings.append(
                    _finding(
                        ValidationCategory.DUPLICATE,
                        ValidationSeverity.ERROR,
                        "DUPLICATE_ID",
                        f"Component id '{c_id}' appears {count} times",
                        reference_api_name=c_id,
                        suggested_action="Ensure component ids are unique",
                        metadata={"count": count},
                    )
                )

        for (c_type, api_name, namespace), count in key_counts.items():
            if count > 1:
                findings.append(
                    _finding(
                        ValidationCategory.DUPLICATE,
                        ValidationSeverity.ERROR,
                        "DUPLICATE_CANONICAL_KEY",
                        f"Duplicate canonical key "
                        f"({c_type}, {api_name}, namespace='{namespace}') "
                        f"appears {count} times",
                        reference_type=c_type,
                        reference_api_name=api_name,
                        suggested_action="Remove duplicate rows for the key",
                        metadata={"count": count},
                    )
                )
        return findings


class ConsistencyRule:
    """Cross-reference validation: referenced components must exist."""

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        objects = registry.get("Object", set())
        all_names = registry.get("*", set())

        for c in components:
            c_type = to_pascal_type(c.type)

            # 1. Parent-object references.
            for key in _OBJECT_REFERENCE_TYPES.get(c_type, ()):
                ref = read_prop(c, key)
                if ref:
                    for target in _as_list(ref):
                        if target not in objects:
                            findings.append(
                                _finding(
                                    ValidationCategory.CONSISTENCY,
                                    ValidationSeverity.ERROR,
                                    "BROKEN_REFERENCE",
                                    f"{c_type} '{c.api_name}' references object "
                                    f"'{target}' which is not present",
                                    component=c,
                                    reference_type="Object",
                                    reference_api_name=str(target),
                                    suggested_action=(
                                        "Include the referenced object in the "
                                        "sync or fix the reference"
                                    ),
                                )
                            )

            # 2. Field lookups / master-details reference target objects.
            if c_type == "Field":
                field_type = read_prop(c, "field_type", "fieldType")
                refs = read_prop(c, "reference_to", "referenceTo")
                for target in _as_list(refs):
                    if target not in objects:
                        findings.append(
                            _finding(
                                ValidationCategory.CONSISTENCY,
                                ValidationSeverity.ERROR,
                                "BROKEN_REFERENCE",
                                f"Field '{c.api_name}' lookup/master-detail "
                                f"references object '{target}' which is not present",
                                component=c,
                                reference_type="Object",
                                reference_api_name=str(target),
                                suggested_action="Fix or include the referenced object",
                            )
                        )
                if (
                    str(field_type or "").lower() in {"lookup", "master_detail"}
                    and not refs
                ):
                    findings.append(
                        _finding(
                            ValidationCategory.CONSISTENCY,
                            ValidationSeverity.WARNING,
                            "MISSING_REFERENCE_TO",
                            f"Field '{c.api_name}' is {field_type} but has no "
                            f"reference_to target",
                            component=c,
                            suggested_action="Set reference_to for the lookup field",
                        )
                    )

            # 3. Formula → parent object + referenced field.
            if c_type == "Formula":
                object_name = read_prop(c, "object_api_name")
                field_name = read_prop(c, "field_api_name", "fieldName")
                if field_name:
                    dotted = f"{object_name}.{field_name}" if object_name else str(field_name)
                    fields = registry.get("Field", set())
                    if str(field_name) not in fields and dotted not in fields:
                        findings.append(
                            _finding(
                                ValidationCategory.CONSISTENCY,
                                ValidationSeverity.ERROR,
                                "BROKEN_REFERENCE",
                                f"Formula '{c.api_name}' references field "
                                f"'{field_name}' which is not present",
                                component=c,
                                reference_type="Field",
                                reference_api_name=str(field_name),
                                suggested_action="Fix or include the referenced field",
                            )
                        )

            # 4. Flow record operations reference objects; subflows reference flows.
            if c_type == "Flow":
                for key in ("record_creates", "record_updates", "record_deletes"):
                    for target in _extract_reference_names(
                        read_prop(c, key, _camel_case(key)), ("object", "object_api_name")
                    ):
                        if target not in objects:
                            findings.append(
                                _finding(
                                    ValidationCategory.CONSISTENCY,
                                    ValidationSeverity.ERROR,
                                    "BROKEN_REFERENCE",
                                    f"Flow '{c.api_name}' {key} references object "
                                    f"'{target}' which is not present",
                                    component=c,
                                    reference_type="Object",
                                    reference_api_name=target,
                                    suggested_action="Fix or include the referenced object",
                                )
                            )
                for target in _extract_reference_names(
                    read_prop(c, "subflows"), ("flow", "flow_api_name")
                ):
                    if target not in registry.get("Flow", set()):
                        findings.append(
                            _finding(
                                ValidationCategory.CONSISTENCY,
                                ValidationSeverity.ERROR,
                                "BROKEN_REFERENCE",
                                f"Flow '{c.api_name}' subflow references flow "
                                f"'{target}' which is not present",
                                component=c,
                                reference_type="Flow",
                                reference_api_name=target,
                                suggested_action="Fix or include the referenced flow",
                            )
                        )

            # 5. Role parent reference.
            if c_type == "Role":
                parent = read_prop(c, "parent_role", "parentRole")
                if parent and parent not in registry.get("Role", set()):
                    findings.append(
                        _finding(
                            ValidationCategory.CONSISTENCY,
                            ValidationSeverity.ERROR,
                            "BROKEN_REFERENCE",
                            f"Role '{c.api_name}' references parent role "
                            f"'{parent}' which is not present",
                            component=c,
                            reference_type="Role",
                            reference_api_name=str(parent),
                            suggested_action="Fix or include the parent role",
                        )
                    )

            # 6. Permission sets / profiles object permissions.
            if c_type in {"PermissionSet", "Profile"}:
                for target in _extract_reference_names(
                    read_prop(c, "object_permissions", "objectPermissions"),
                    ("object", "object_api_name", "sobject"),
                ):
                    if target not in objects:
                        findings.append(
                            _finding(
                                ValidationCategory.CONSISTENCY,
                                ValidationSeverity.ERROR,
                                "BROKEN_REFERENCE",
                                f"{c_type} '{c.api_name}' grants permission on "
                                f"object '{target}' which is not present",
                                component=c,
                                reference_type="Object",
                                reference_api_name=target,
                                suggested_action="Fix or include the referenced object",
                            )
                        )

            # 7. Dashboard components reference reports.
            if c_type == "Dashboard":
                for target in _extract_reference_names(
                    read_prop(c, "components"),
                    ("report", "report_api_name", "name"),
                ):
                    if target not in registry.get("Report", set()):
                        findings.append(
                            _finding(
                                ValidationCategory.CONSISTENCY,
                                ValidationSeverity.ERROR,
                                "BROKEN_REFERENCE",
                                f"Dashboard '{c.api_name}' references report "
                                f"'{target}' which is not present",
                                component=c,
                                reference_type="Report",
                                reference_api_name=target,
                                suggested_action="Fix or include the referenced report",
                            )
                        )

            # 8. Declared canonical relationships.
            for rel in c.relationships or []:
                target = rel.target_api_name
                if target and target not in all_names:
                    findings.append(
                        _finding(
                            ValidationCategory.RELATIONSHIP,
                            ValidationSeverity.ERROR,
                            "BROKEN_REFERENCE",
                            f"{c_type} '{c.api_name}' relationship targets "
                            f"'{target}' which is not present",
                            component=c,
                            reference_type=rel.target_type or "MetadataComponent",
                            reference_api_name=target,
                            suggested_action="Fix or include the relationship target",
                        )
                    )

        return findings


class IntegrityRule:
    """Orphans and missing reference data.

    * A child component whose parent object is absent is an orphan.
    * A component type that *requires* a parent-object reference but carries NO
      reference data at all is an integrity failure — this is how the engine
      detects the repository read-path loss of type-specific fields.
    """

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        objects = registry.get("Object", set())

        for c in components:
            c_type = to_pascal_type(c.type)
            required_keys = _OBJECT_REFERENCE_TYPES.get(c_type, ())
            if not required_keys:
                continue

            ref = read_prop(c, *required_keys)
            if not ref:
                findings.append(
                    _finding(
                        ValidationCategory.INTEGRITY,
                        ValidationSeverity.ERROR,
                        "REFERENCE_DATA_MISSING",
                        f"{c_type} '{c.api_name}' requires a parent-object "
                        f"reference ({required_keys[0]}) but no reference data "
                        f"was returned by the repository",
                        component=c,
                        reference_type="Object",
                        suggested_action=(
                            "Persist type-specific fields in metadata_properties "
                            "and restore them on the repository read path "
                            "(_orm_to_component)"
                        ),
                    )
                )
                continue

            for target in _as_list(ref):
                if target and target not in objects:
                    findings.append(
                        _finding(
                            ValidationCategory.ORPHAN,
                            ValidationSeverity.ERROR,
                            f"ORPHANED_{c_type.upper()}",
                            f"{c_type} '{c.api_name}' is orphaned: parent object "
                            f"'{target}' is not present in the repository",
                            component=c,
                            reference_type="Object",
                            reference_api_name=str(target),
                            suggested_action=(
                                "Include the parent object or remove the orphan"
                            ),
                        )
                    )
        return findings


class CanonicalRule:
    """Run the existing canonical validation rules against the batch.

    The repository read path returns PascalCase type names while the canonical
    validator's KnownTypeRule expects snake_case, so types are mapped before
    running. Typed-class rules (parent reference, role circularity) are no-ops
    on base components returned by the repository; this is surfaced as a note.
    """

    def __init__(self, validator: IMetadataValidator) -> None:
        self._validator = validator

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        if not components:
            return findings

        # Shallow copies with snake_case types so KnownTypeRule recognizes them.
        mapped: list[MetadataComponent] = []
        for c in components:
            copy = c.model_copy(deep=False)
            copy.type = to_snake_type(c.type)
            mapped.append(copy)

        report = self._validator.validate(mapped)
        for result in report.results:
            if result.severity not in ("error", "warning"):
                continue
            findings.append(
                ValidationFinding(
                    category=ValidationCategory.CANONICAL,
                    severity=(
                        ValidationSeverity.ERROR
                        if result.severity == "error"
                        else ValidationSeverity.WARNING
                    ),
                    error_code=result.error_code,
                    message=result.message,
                    component_type=result.component_type,
                    api_name=result.api_name,
                    reference_api_name=result.api_name,
                    suggested_action=result.suggested_action or "",
                    metadata=dict(result.metadata),
                )
            )
        return findings


class UnsupportedTypeRule:
    """Report metadata types in the validation matrix with no repository table."""

    def validate(
        self,
        components: list[MetadataComponent],
        *,
        registry: dict[str, set[str]],
        downloaded_counts: dict[str, int] | None,
    ) -> list[ValidationFinding]:
        findings: list[ValidationFinding] = []
        for unsupported in _UNSUPPORTED_TYPES:
            findings.append(
                _finding(
                    ValidationCategory.UNSUPPORTED,
                    ValidationSeverity.INFO,
                    "UNSUPPORTED_TYPE",
                    f"Metadata type '{unsupported}' is in the validation matrix "
                    f"but has no ORM table / repository representation; skipped",
                    reference_type=unsupported,
                )
            )
        return findings


def default_rule_set(validator: IMetadataValidator | None = None) -> ValidationRuleSet:
    """Build the standard Phase 3.5 rule set."""
    rule_set = ValidationRuleSet()
    rule_set.register(CompletenessRule())
    rule_set.register(DuplicateRule())
    rule_set.register(ConsistencyRule())
    rule_set.register(IntegrityRule())
    if validator is not None:
        rule_set.register(CanonicalRule(validator))
    rule_set.register(UnsupportedTypeRule())
    return rule_set
