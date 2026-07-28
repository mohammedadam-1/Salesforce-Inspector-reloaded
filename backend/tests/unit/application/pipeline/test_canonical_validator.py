from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from sfir_backend.application.pipeline.validator import (
    CanonicalMetadataValidator,
    IValidationRule,
    ValidationReport,
    ValidationResult,
)
from sfir_backend.application.pipeline.validator.rules import (
    ApiNameFormatRule,
    DuplicateApiNameRule,
    EmptyRequiredFieldRule,
    EnumValueRule,
    KnownTypeRule,
    ParentReferenceRule,
    RequiredIdentifiersRule,
    RoleCircularReferenceRule,
    VersionRangeRule,
)
from sfir_backend.domain.canonical.access import (
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.base import (
    FieldType,
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import (
    MetadataField,
    MetadataObject,
    MetadataRelationship,
)
from sfir_backend.domain.canonical.layouts import (
    MetadataLayout,
    MetadataRecordType,
)
from sfir_backend.domain.canonical.reporting import MetadataReport
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)


def _make_id() -> str:
    return str(uuid.uuid4())


def _make_org_id() -> str:
    return str(uuid.uuid4())


def _component(**kwargs: Any) -> MetadataComponent:
    cls = kwargs.pop("_class", MetadataApexClass)
    defaults: dict[str, Any] = dict(
        id=_make_id(),
        organization_id=_make_org_id(),
        type="apex_class",
        api_name="TestClass",
        label="Test Class",
        version=1,
    )
    if cls in (MetadataApexClass, MetadataTrigger):
        defaults["body"] = "class Test {}"
    defaults.update(kwargs)
    try:
        return cls(**defaults)
    except Exception:
        return cls.model_construct(**defaults)


# ---------------------------------------------------------------------------
# ValidationResult / ValidationReport
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_default_values(self) -> None:
        r = ValidationResult(severity="error", error_code="TEST", message="msg", component_id="c1", component_type="t1", api_name="a1")
        assert r.severity == "error"
        assert r.error_code == "TEST"
        assert r.field_name is None
        assert r.suggested_action is None
        assert r.metadata == {}

    def test_with_all_fields(self) -> None:
        r = ValidationResult(
            severity="warning",
            error_code="WARN",
            message="warning msg",
            component_id="c2",
            component_type="t2",
            api_name="a2",
            field_name="name",
            suggested_action="Fix it",
            metadata={"key": "val"},
        )
        assert r.severity == "warning"
        assert r.field_name == "name"
        assert r.suggested_action == "Fix it"
        assert r.metadata["key"] == "val"


class TestValidationReport:
    def test_default_values(self) -> None:
        report = ValidationReport()
        assert report.results == []
        assert report.valid == []
        assert report.invalid == []

    def test_with_data(self) -> None:
        c = _component()
        r = ValidationResult(severity="error", error_code="E1", message="err", component_id=c.id, component_type=c.type, api_name=c.api_name)
        report = ValidationReport(
            results=[r],
            valid=[c],
            invalid=[(c, [r])],
        )
        assert len(report.results) == 1
        assert len(report.valid) == 1
        assert len(report.invalid) == 1


# ---------------------------------------------------------------------------
# RequiredIdentifiersRule
# ---------------------------------------------------------------------------


class TestRequiredIdentifiersRule:
    @pytest.fixture
    def rule(self) -> RequiredIdentifiersRule:
        return RequiredIdentifiersRule()

    def test_valid_component(self, rule: RequiredIdentifiersRule) -> None:
        c = _component()
        results = rule.validate([c])
        assert len(results) == 0

    def test_missing_id(self, rule: RequiredIdentifiersRule) -> None:
        c = _component(id="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "MISSING_ID" in codes

    def test_missing_type(self, rule: RequiredIdentifiersRule) -> None:
        c = _component(type="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "MISSING_TYPE" in codes

    def test_missing_api_name(self, rule: RequiredIdentifiersRule) -> None:
        c = _component(api_name="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "MISSING_API_NAME" in codes

    def test_whitespace_only_id(self, rule: RequiredIdentifiersRule) -> None:
        c = _component(id="  ")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "MISSING_ID" in codes

    def test_all_missing(self, rule: RequiredIdentifiersRule) -> None:
        c = _component(id="", type="", api_name="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "MISSING_ID" in codes
        assert "MISSING_TYPE" in codes
        assert "MISSING_API_NAME" in codes

    def test_can_handle_always_true(self, rule: RequiredIdentifiersRule) -> None:
        assert rule.can_handle(_component()) is True


# ---------------------------------------------------------------------------
# KnownTypeRule
# ---------------------------------------------------------------------------


class TestKnownTypeRule:
    @pytest.fixture
    def rule(self) -> KnownTypeRule:
        return KnownTypeRule()

    def test_known_type_passes(self, rule: KnownTypeRule) -> None:
        c = _component(type="apex_class")
        assert len(rule.validate([c])) == 0

    def test_unknown_type_warns(self, rule: KnownTypeRule) -> None:
        c = _component(type="unknown_type_xyz")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "UNKNOWN_TYPE" in codes

    def test_known_types_pass(self, rule: KnownTypeRule) -> None:
        known = [
            "apex_class", "trigger", "object", "field", "relationship",
            "global_value_set", "validation_rule", "formula", "flow",
            "flow_version", "layout", "record_type", "profile",
            "permission_set", "role", "queue", "public_group",
            "sharing_rule", "email_template", "named_credential",
            "connected_app", "report", "dashboard", "lightning_page",
            "quick_action", "custom_metadata", "custom_setting",
            "workflow", "approval_process",
        ]
        for t in known:
            c = _component(type=t)
            errors = [r for r in rule.validate([c]) if r.severity == "error"]
            assert len(errors) == 0, f"Type '{t}' should be known"

    def test_empty_type_skipped(self, rule: KnownTypeRule) -> None:
        c = _component(type="")
        # Empty type will be caught by RequiredIdentifiersRule, not here
        results = rule.validate([c])
        unknown = [r for r in results if r.error_code == "UNKNOWN_TYPE"]
        assert len(unknown) == 0


# ---------------------------------------------------------------------------
# ApiNameFormatRule
# ---------------------------------------------------------------------------


class TestApiNameFormatRule:
    @pytest.fixture
    def rule(self) -> ApiNameFormatRule:
        return ApiNameFormatRule()

    def test_valid_api_names(self, rule: ApiNameFormatRule) -> None:
        names = ["Test", "Test__c", "MyClass", "a.b.c", "_private", "A1_B2"]
        for name in names:
            c = _component(api_name=name)
            assert len(rule.validate([c])) == 0, f"'{name}' should be valid"

    def test_invalid_api_names(self, rule: ApiNameFormatRule) -> None:
        names = ["with space", "has-hyphen", "123starts_with_digit", "has$ymbol"]
        for name in names:
            c = _component(api_name=name)
            results = rule.validate([c])
            codes = {r.error_code for r in results}
            assert "INVALID_API_NAME" in codes, f"'{name}' should be invalid"

    def test_empty_api_name_not_error(self, rule: ApiNameFormatRule) -> None:
        # Empty will be caught by RequiredIdentifiersRule
        c = _component(api_name="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "INVALID_API_NAME" not in codes


# ---------------------------------------------------------------------------
# DuplicateApiNameRule
# ---------------------------------------------------------------------------


class TestDuplicateApiNameRule:
    @pytest.fixture
    def rule(self) -> DuplicateApiNameRule:
        return DuplicateApiNameRule()

    def test_no_duplicates(self, rule: DuplicateApiNameRule) -> None:
        c1 = _component(api_name="Class1", type="apex_class")
        c2 = _component(api_name="Class2", type="apex_class")
        assert len(rule.validate([c1, c2])) == 0

    def test_duplicate_api_name(self, rule: DuplicateApiNameRule) -> None:
        c1 = _component(api_name="Duplicate", type="apex_class")
        c2 = _component(api_name="Duplicate", type="apex_class")
        results = rule.validate([c1, c2])
        codes = {r.error_code for r in results}
        assert "DUPLICATE_API_NAME" in codes

    def test_same_name_different_type(self, rule: DuplicateApiNameRule) -> None:
        c1 = _component(api_name="Name", type="apex_class")
        c2 = _component(api_name="Name", type="trigger")
        results = rule.validate([c1, c2])
        codes = {r.error_code for r in results}
        assert "DUPLICATE_API_NAME" not in codes

    def test_several_duplicates(self, rule: DuplicateApiNameRule) -> None:
        components = [
            _component(id="1", api_name="A", type="apex_class"),
            _component(id="2", api_name="A", type="apex_class"),
            _component(id="3", api_name="B", type="apex_class"),
            _component(id="4", api_name="B", type="apex_class"),
            _component(id="5", api_name="A", type="apex_class"),
        ]
        results = rule.validate(components)
        ids_with_error = {r.component_id for r in results}
        for c in components:
            assert c.id in ids_with_error


# ---------------------------------------------------------------------------
# ParentReferenceRule
# ---------------------------------------------------------------------------


class TestParentReferenceRule:
    @pytest.fixture
    def rule(self) -> ParentReferenceRule:
        return ParentReferenceRule()

    def test_no_parent_references(self, rule: ParentReferenceRule) -> None:
        c = _component(_class=MetadataApexClass, type="apex_class")
        assert len(rule.validate([c])) == 0

    def test_parent_object_present(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="MyObj", type="object", _class=MetadataObject)
        trigger = _component(id="t1", api_name="MyTrigger", type="trigger", _class=MetadataTrigger, object_api_name="MyObj")
        results = rule.validate([obj, trigger])
        assert len(results) == 0

    def test_parent_object_missing(self, rule: ParentReferenceRule) -> None:
        trigger = _component(id="t1", api_name="MyTrigger", type="trigger", _class=MetadataTrigger, object_api_name="NonExistentObj")
        results = rule.validate([trigger])
        codes = {r.error_code for r in results}
        assert "MISSING_PARENT_OBJECT" in codes

    def test_parent_role_present(self, rule: ParentReferenceRule) -> None:
        parent = _component(id="r1", api_name="ParentRole", type="role", _class=MetadataRole)
        child = _component(id="r2", api_name="ChildRole", type="role", _class=MetadataRole, parent_role="ParentRole")
        results = rule.validate([parent, child])
        assert len(results) == 0

    def test_parent_role_missing(self, rule: ParentReferenceRule) -> None:
        child = _component(id="r2", api_name="ChildRole", type="role", _class=MetadataRole, parent_role="MissingRole")
        results = rule.validate([child])
        codes = {r.error_code for r in results}
        assert "MISSING_PARENT_ROLE" in codes

    def test_missing_reference_is_warning_not_error(self, rule: ParentReferenceRule) -> None:
        trigger = _component(id="t1", api_name="MyTrigger", type="trigger", _class=MetadataTrigger, object_api_name="Missing")
        results = rule.validate([trigger])
        assert all(r.severity == "warning" for r in results)

    def test_layout_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        layout = _component(id="l1", api_name="Obj-Layout", type="layout", _class=MetadataLayout, object_api_name="Obj")
        results = rule.validate([obj, layout])
        assert len(results) == 0

    def test_record_type_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        rt = _component(id="rt1", api_name="Obj.RT1", type="record_type", _class=MetadataRecordType, object_api_name="Obj")
        results = rule.validate([obj, rt])
        assert len(results) == 0

    def test_validation_rule_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        vr = _component(id="vr1", api_name="Obj_VR1", type="validation_rule", _class=MetadataValidationRule, object_api_name="Obj", formula="True")
        results = rule.validate([obj, vr])
        assert len(results) == 0

    def test_workflow_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        wf = _component(id="wf1", api_name="Obj_WF1", type="workflow", _class=MetadataWorkflow, object_api_name="Obj")
        results = rule.validate([obj, wf])
        assert len(results) == 0

    def test_approval_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        ap = _component(id="ap1", api_name="Obj_AP1", type="approval_process", _class=MetadataApprovalProcess, object_api_name="Obj")
        results = rule.validate([obj, ap])
        assert len(results) == 0

    def test_report_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        rpt = _component(id="rpt1", api_name="Obj_Rpt", type="report", _class=MetadataReport, object_api_name="Obj")
        results = rule.validate([obj, rpt])
        assert len(results) == 0

    def test_sharing_rule_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        sr = _component(id="sr1", api_name="Obj_SR1", type="sharing_rule", _class=MetadataSharingRule, object_api_name="Obj")
        results = rule.validate([obj, sr])
        assert len(results) == 0

    def test_field_with_object(self, rule: ParentReferenceRule) -> None:
        obj = _component(id="o1", api_name="Obj", type="object", _class=MetadataObject)
        field = _component(id="f1", api_name="Obj.Field__c", type="field", _class=MetadataField, object_api_name="Obj")
        results = rule.validate([obj, field])
        assert len(results) == 0

    def test_field_without_object(self, rule: ParentReferenceRule) -> None:
        field = _component(id="f1", api_name="Field__c", type="field", _class=MetadataField, object_api_name="Missing")
        results = rule.validate([field])
        codes = {r.error_code for r in results}
        assert "MISSING_PARENT_OBJECT" in codes


# ---------------------------------------------------------------------------
# RoleCircularReferenceRule
# ---------------------------------------------------------------------------


class TestRoleCircularReferenceRule:
    @pytest.fixture
    def rule(self) -> RoleCircularReferenceRule:
        return RoleCircularReferenceRule()

    def test_no_circular_reference(self, rule: RoleCircularReferenceRule) -> None:
        roles = [
            _component(id="r1", api_name="CEO", type="role", _class=MetadataRole, parent_role=""),
            _component(id="r2", api_name="VP", type="role", _class=MetadataRole, parent_role="CEO"),
            _component(id="r3", api_name="Manager", type="role", _class=MetadataRole, parent_role="VP"),
        ]
        assert len(rule.validate(roles)) == 0

    def test_direct_circular(self, rule: RoleCircularReferenceRule) -> None:
        roles = [
            _component(id="r1", api_name="RoleA", type="role", _class=MetadataRole, parent_role="RoleA"),
        ]
        results = rule.validate(roles)
        codes = {r.error_code for r in results}
        assert "CIRCULAR_PARENT_ROLE" in codes

    def test_indirect_circular(self, rule: RoleCircularReferenceRule) -> None:
        roles = [
            _component(id="r1", api_name="RoleA", type="role", _class=MetadataRole, parent_role="RoleB"),
            _component(id="r2", api_name="RoleB", type="role", _class=MetadataRole, parent_role="RoleC"),
            _component(id="r3", api_name="RoleC", type="role", _class=MetadataRole, parent_role="RoleA"),
        ]
        results = rule.validate(roles)
        codes = {r.error_code for r in results}
        assert "CIRCULAR_PARENT_ROLE" in codes

    def test_no_role_components_skipped(self, rule: RoleCircularReferenceRule) -> None:
        c = _component(type="apex_class")
        assert len(rule.validate([c])) == 0


# ---------------------------------------------------------------------------
# EnumValueRule
# ---------------------------------------------------------------------------


class TestEnumValueRule:
    @pytest.fixture
    def rule(self) -> EnumValueRule:
        return EnumValueRule()

    def test_valid_enums(self, rule: EnumValueRule) -> None:
        c = _component(
            source_platform=SourcePlatform.SALESFORCE,
            status=MetadataStatus.ACTIVE,
        )
        assert len(rule.validate([c])) == 0

    def test_invalid_source_platform(self, rule: EnumValueRule) -> None:
        c = _component(source_platform="invalid_platform")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "INVALID_ENUM_VALUE" in codes
        fields = {r.field_name for r in results}
        assert "source_platform" in fields

    def test_invalid_status(self, rule: EnumValueRule) -> None:
        c = _component(status="invalid_status")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "INVALID_ENUM_VALUE" in codes
        fields = {r.field_name for r in results}
        assert "status" in fields

    def test_none_enums_skipped(self, rule: EnumValueRule) -> None:
        c = _component(source_platform=None, status=None)
        assert len(rule.validate([c])) == 0


# ---------------------------------------------------------------------------
# EmptyRequiredFieldRule
# ---------------------------------------------------------------------------


class TestEmptyRequiredFieldRule:
    @pytest.fixture
    def rule(self) -> EmptyRequiredFieldRule:
        return EmptyRequiredFieldRule()

    def test_apex_class_with_body(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(_class=MetadataApexClass, type="apex_class", body="class Test {}")
        assert len(rule.validate([c])) == 0

    def test_apex_class_empty_body(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(_class=MetadataApexClass, type="apex_class", body="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "EMPTY_REQUIRED_FIELD" in codes

    def test_trigger_with_body(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(_class=MetadataTrigger, type="trigger", body="trigger Test on Obj() {}")
        assert len(rule.validate([c])) == 0

    def test_trigger_empty_body(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(_class=MetadataTrigger, type="trigger", body="")
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "EMPTY_REQUIRED_FIELD" in codes

    def test_validation_rule_with_formula(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(
            _class=MetadataValidationRule,
            type="validation_rule",
            object_api_name="Obj",
            formula="True",
        )
        assert len(rule.validate([c])) == 0

    def test_validation_rule_empty_formula(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(
            _class=MetadataValidationRule,
            type="validation_rule",
            object_api_name="Obj",
            formula="",
        )
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "EMPTY_REQUIRED_FIELD" in codes

    def test_validation_rule_empty_object_api_name(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(
            _class=MetadataValidationRule,
            type="validation_rule",
            object_api_name="",
            formula="True",
        )
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "EMPTY_REQUIRED_FIELD" in codes

    def test_non_apex_component_skipped(self, rule: EmptyRequiredFieldRule) -> None:
        c = _component(_class=MetadataObject, type="object")
        assert len(rule.validate([c])) == 0


# ---------------------------------------------------------------------------
# VersionRangeRule
# ---------------------------------------------------------------------------


class TestVersionRangeRule:
    @pytest.fixture
    def rule(self) -> VersionRangeRule:
        return VersionRangeRule()

    def test_valid_version(self, rule: VersionRangeRule) -> None:
        c = _component(version=1)
        assert len(rule.validate([c])) == 0

    def test_valid_high_version(self, rule: VersionRangeRule) -> None:
        c = _component(version=999)
        assert len(rule.validate([c])) == 0

    def test_invalid_version_zero(self, rule: VersionRangeRule) -> None:
        c = _component(version=0)
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "INVALID_VERSION" in codes

    def test_invalid_version_negative(self, rule: VersionRangeRule) -> None:
        c = _component(version=-1)
        results = rule.validate([c])
        codes = {r.error_code for r in results}
        assert "INVALID_VERSION" in codes


# ---------------------------------------------------------------------------
# CanonicalMetadataValidator
# ---------------------------------------------------------------------------


class TestCanonicalMetadataValidator:
    @pytest.fixture
    def validator(self) -> CanonicalMetadataValidator:
        v = CanonicalMetadataValidator()
        v.register(RequiredIdentifiersRule())
        v.register(ApiNameFormatRule())
        v.register(DuplicateApiNameRule())
        v.register(KnownTypeRule())
        v.register(ParentReferenceRule())
        v.register(RoleCircularReferenceRule())
        v.register(EnumValueRule())
        v.register(EmptyRequiredFieldRule())
        v.register(VersionRangeRule())
        return v

    def test_valid_component_passes(self, validator: CanonicalMetadataValidator) -> None:
        c = _component()
        report = validator.validate([c])
        assert len(report.valid) == 1
        assert len(report.invalid) == 0
        assert len(report.results) == 0

    def test_empty_list(self, validator: CanonicalMetadataValidator) -> None:
        report = validator.validate([])
        assert len(report.valid) == 0
        assert len(report.invalid) == 0

    def test_invalid_component_fails(self, validator: CanonicalMetadataValidator) -> None:
        c = _component(api_name="invalid name with spaces")
        report = validator.validate([c])
        assert len(report.valid) == 0
        assert len(report.invalid) == 1
        assert len(report.results) >= 1

    def test_batch_mixed_valid_invalid(self, validator: CanonicalMetadataValidator) -> None:
        valid = _component(id="v1", api_name="ValidClass")
        invalid = _component(id="i1", api_name="invalid name")
        report = validator.validate([valid, invalid])
        assert len(report.valid) == 1
        assert len(report.invalid) == 1
        assert report.valid[0].id == "v1"
        assert report.invalid[0][0].id == "i1"

    def test_deterministic_ordering(self, validator: CanonicalMetadataValidator) -> None:
        c1 = _component(id="c1", api_name="Valid1")
        c2 = _component(id="c2", api_name="Valid2")
        c3 = _component(id="c3", api_name="Valid3")
        report1 = validator.validate([c1, c2, c3])
        report2 = validator.validate([c1, c2, c3])
        assert [v.id for v in report1.valid] == [v.id for v in report2.valid]
        assert len(report1.results) == len(report2.results)

    def test_immutability(self, validator: CanonicalMetadataValidator) -> None:
        c = _component(id="c1", api_name="Test", body="class Test {}")
        original_id = c.id
        original_api = c.api_name
        validator.validate([c])
        assert c.id == original_id
        assert c.api_name == original_api

    def test_large_batch(self, validator: CanonicalMetadataValidator) -> None:
        components = [_component(id=f"c{i}", api_name=f"Class{i}") for i in range(1000)]
        report = validator.validate(components)
        assert len(report.valid) == 1000
        assert len(report.invalid) == 0

    def test_rule_failure_handled_gracefully(self, validator: CanonicalMetadataValidator) -> None:
        class FailingRule(IValidationRule):
            def can_handle(self, component: MetadataComponent) -> bool:
                return True

            def validate(self, components: list[MetadataComponent]) -> list[ValidationResult]:
                raise RuntimeError("Unexpected failure")

        validator.register(FailingRule())
        c = _component()
        report = validator.validate([c])
        codes = {r.error_code for r in report.results}
        assert "RULE_FAILURE" in codes

    def test_multiple_errors_on_same_component(self, validator: CanonicalMetadataValidator) -> None:
        c = _component(id="", type="", api_name="", version=0)
        report = validator.validate([c])
        assert len(report.invalid) == 1
        assert len(report.invalid[0][1]) >= 1

    def test_no_rules_registered(self) -> None:
        v = CanonicalMetadataValidator()
        c = _component()
        report = v.validate([c])
        assert len(report.valid) == 1
        assert len(report.invalid) == 0

    def test_deduplication_of_errors(self, validator: CanonicalMetadataValidator) -> None:
        c = _component(api_name="has space")
        report = validator.validate([c])
        # Should have at least one error result
        error_results = [r for r in report.results if r.severity == "error"]
        assert len(error_results) >= 1
        # Component should be in invalid list
        assert len(report.invalid) == 1


# ---------------------------------------------------------------------------
# ValidationStage Integration
# ---------------------------------------------------------------------------


class TestValidationStage:
    @pytest.mark.asyncio
    async def test_stage_updates_context(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import ValidationStage

        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        stage = ValidationStage(validator=validator)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.canonical_components = [_component(id="c1", api_name="ValidClass", body="class Test {}")]
        result = await stage.execute(ctx)
        assert len(result.validated_components) == 1
        assert len(result.validation_results) == 0
        assert len(result.validation_errors) == 0

    @pytest.mark.asyncio
    async def test_stage_no_canonical_components(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import ValidationStage

        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        stage = ValidationStage(validator=validator)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        result = await stage.execute(ctx)
        assert len(result.validated_components) == 0

    @pytest.mark.asyncio
    async def test_stage_invalid_components(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import ValidationStage

        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        stage = ValidationStage(validator=validator)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.canonical_components = [
            _component(id="c1", api_name="ValidClass", body="class Test {}"),
            _component(id="c2", api_name=""),  # missing api_name
        ]
        result = await stage.execute(ctx)
        assert len(result.validated_components) == 1
        assert len(result.validation_results) >= 1
        assert len(result.validation_errors) >= 1

    @pytest.mark.asyncio
    async def test_stage_all_invalid(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import ValidationStage

        validator = CanonicalMetadataValidator()
        validator.register(RequiredIdentifiersRule())
        stage = ValidationStage(validator=validator)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.canonical_components = [
            _component(id="", api_name=""),  # all missing identifiers
        ]
        result = await stage.execute(ctx)
        assert len(result.validated_components) == 0
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_stage_exception_handled(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import ValidationStage

        class ExplodingValidator:  # Does not implement IMetadataValidator
            def validate(self, components: list[MetadataComponent]) -> ValidationReport:
                raise RuntimeError("Boom")

        stage = ValidationStage(validator=ExplodingValidator())  # type: ignore[arg-type]

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.canonical_components = [_component()]
        result = await stage.execute(ctx)
        assert len(result.errors) >= 1
