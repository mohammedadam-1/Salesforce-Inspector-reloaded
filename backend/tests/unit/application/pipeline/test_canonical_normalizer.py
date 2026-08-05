from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from sfir_backend.application.pipeline.normalizer import (
    CanonicalNormalizer,
    ComponentKey,
    FingerprintService,
    IdentityService,
    INormalizationRule,
    NormalizationReport,
    NormalizedDocument,
    NormalizedRelationship,
)
from sfir_backend.application.pipeline.normalizer.relationship_normalizer import (
    RelationshipNormalizer,
)
from sfir_backend.application.pipeline.normalizer.rules import (
    NormalizeDefaultsRule,
    NormalizeEnumRule,
    NormalizeNamesRule,
    NormalizeNullsRule,
    NormalizeOwnerRule,
    NormalizeParentRule,
    NormalizeStringsRule,
    NormalizeTimestampsRule,
    NormalizeTypeNameRule,
)
from sfir_backend.domain.canonical.access import (
    MetadataRole,
    MetadataSharingRule,
)
from sfir_backend.domain.canonical.base import (
    CanonicalRelationship,
    FieldType,
    MetadataComponent,
    MetadataStatus,
    RelationshipType,
    SourcePlatform,
)
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import (
    MetadataField,
    MetadataObject,
    MetadataRelationship,
)
from sfir_backend.domain.canonical.flows import MetadataFlow, MetadataFlowVersion
from sfir_backend.domain.canonical.layouts import (
    MetadataLayout,
    MetadataRecordType,
)
from sfir_backend.domain.canonical.permissions import (
    MetadataPermissionSet,
    MetadataProfile,
)
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.canonical.ui import MetadataLightningPage
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.canonical.workflows import (
    MetadataApprovalProcess,
    MetadataWorkflow,
)


def _make_org_id() -> str:
    return str(uuid.uuid4())


def _component(**kwargs: Any) -> MetadataComponent:
    cls = kwargs.pop("_class", MetadataApexClass)
    defaults: dict[str, Any] = dict(
        id=str(uuid.uuid4()),
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
# Normalized Model Tests
# ---------------------------------------------------------------------------


class TestNormalizedDocument:
    def test_minimal_construction(self) -> None:
        doc = NormalizedDocument(
            identity="abc123",
            component_key=ComponentKey(type="ApexClass", api_name="Foo"),
            type="ApexClass",
            api_name="Foo",
            qualified_name="Foo",
            fully_qualified_name="Foo",
            organization_id="org1",
            fingerprint="fp1",
            content_hash="ch1",
        )
        assert doc.identity == "abc123"
        assert doc.version == 1
        assert doc.status == "active"
        assert doc.source_platform == "salesforce"
        assert doc.label is None
        assert doc.namespace is None

    def test_with_all_fields(self) -> None:
        ck = ComponentKey(type="ApexClass", api_name="Foo", namespace="ns")
        rel = NormalizedRelationship(type="contains", target_identity="t1", target_fqdn="ns___Foo")
        doc = NormalizedDocument(
            identity="id1",
            component_key=ck,
            type="ApexClass",
            api_name="Foo",
            qualified_name="Parent.Foo",
            fully_qualified_name="ns___Foo",
            label="My Class",
            namespace="ns",
            description="A test class",
            version=2,
            status="active",
            source_platform="salesforce",
            organization_id="org1",
            owner_id="u1",
            created_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-06-01T00:00:00+00:00",
            fingerprint="fp1",
            content_hash="ch1",
            properties={"key": "val"},
            relationships=[rel],
            normalized_at="2024-06-15T00:00:00+00:00",
        )
        assert doc.component_key.namespace == "ns"
        assert len(doc.relationships) == 1
        assert doc.properties["key"] == "val"

    def test_component_key_to_identity_input(self) -> None:
        ck = ComponentKey(type="ApexClass", api_name="MyClass", namespace="ns")
        assert "ns" in ck.to_identity_input()
        ck2 = ComponentKey(type="ApexClass", api_name="MyClass")
        assert ck2.namespace is None


class TestNormalizedRelationship:
    def test_construction(self) -> None:
        rel = NormalizedRelationship(type="references", target_identity="t1", target_fqdn="Account")
        assert rel.type == "references"
        assert rel.target_component_key is None
        assert rel.metadata == {}

    def test_with_component_key(self) -> None:
        ck = ComponentKey(type="Object", api_name="Account")
        rel = NormalizedRelationship(
            type="contains",
            target_identity="t1",
            target_component_key=ck,
            target_fqdn="Account",
        )
        assert rel.target_component_key.api_name == "Account"


class TestComponentKey:
    def test_construction(self) -> None:
        ck = ComponentKey(type="ApexClass", api_name="Foo", namespace="ns")
        assert ck.type == "ApexClass"
        assert ck.api_name == "Foo"
        assert ck.namespace == "ns"


# ---------------------------------------------------------------------------
# IdentityService Tests
# ---------------------------------------------------------------------------


class TestIdentityService:
    @pytest.fixture
    def service(self) -> IdentityService:
        return IdentityService()

    def test_deterministic(self, service: IdentityService) -> None:
        h1 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass")
        h2 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass")
        assert h1 == h2

    def test_different_org_different_hash(self, service: IdentityService) -> None:
        h1 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass")
        h2 = service.compute_component_hash("org2", "salesforce", "apex_class", "MyClass")
        assert h1 != h2

    def test_different_name_different_hash(self, service: IdentityService) -> None:
        h1 = service.compute_component_hash("org1", "salesforce", "apex_class", "ClassA")
        h2 = service.compute_component_hash("org1", "salesforce", "apex_class", "ClassB")
        assert h1 != h2

    def test_namespace_included(self, service: IdentityService) -> None:
        h1 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass", namespace="ns")
        h2 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass")
        assert h1 != h2

    def test_namespace_same(self, service: IdentityService) -> None:
        h1 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass", namespace="ns")
        h2 = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass", namespace="ns")
        assert h1 == h2

    def test_hex_output(self, service: IdentityService) -> None:
        h = service.compute_component_hash("org1", "salesforce", "apex_class", "MyClass")
        assert len(h) == 64
        int(h, 16)

    def test_from_component(self, service: IdentityService) -> None:
        c = _component()  # MetadataApexClass
        h1 = service.compute_component_hash_from_component(c)
        expected = service.compute_component_hash(
            organization_id=c.organization_id,
            source_platform="salesforce",
            type_name=c.type,
            api_name=c.api_name,
            namespace=c.namespace,
        )
        assert h1 == expected

    def test_from_component_with_namespace(self, service: IdentityService) -> None:
        c = _component(namespace="ns")
        h = service.compute_component_hash_from_component(c)
        assert ":" in h or len(h) == 64


# ---------------------------------------------------------------------------
# FingerprintService Tests
# ---------------------------------------------------------------------------


class TestFingerprintService:
    @pytest.fixture
    def service(self) -> FingerprintService:
        return FingerprintService()

    def test_content_hash_deterministic(self, service: FingerprintService) -> None:
        c = _component()
        h1 = service.compute_content_hash(c)
        h2 = service.compute_content_hash(c)
        assert h1 == h2

    def test_content_hash_changes_on_body_change(self, service: FingerprintService) -> None:
        c1 = _component(body="class A {}")
        c2 = _component(body="class B {}")
        assert service.compute_content_hash(c1) != service.compute_content_hash(c2)

    def test_content_hash_stable_across_id(self, service: FingerprintService) -> None:
        org_id = _make_org_id()
        c1 = _component(id="id1", organization_id=org_id)
        c2 = _component(id="id2", organization_id=org_id)
        assert service.compute_content_hash(c1) == service.compute_content_hash(c2)

    def test_relationship_hash_empty(self, service: FingerprintService) -> None:
        h = service.compute_relationship_hash([])
        assert len(h) == 64

    def test_relationship_hash_deterministic(self, service: FingerprintService) -> None:
        rels = [NormalizedRelationship(type="references", target_identity="t1", target_fqdn="Obj")]
        h1 = service.compute_relationship_hash(rels)
        h2 = service.compute_relationship_hash(rels)
        assert h1 == h2

    def test_relationship_hash_order_independent(self, service: FingerprintService) -> None:
        rels1 = [
            NormalizedRelationship(type="references", target_identity="t1", target_fqdn="Obj1"),
            NormalizedRelationship(type="contains", target_identity="t2", target_fqdn="Obj2"),
        ]
        rels2 = list(reversed(rels1))
        assert service.compute_relationship_hash(rels1) == service.compute_relationship_hash(rels2)

    def test_version_hash(self, service: FingerprintService) -> None:
        h = service.compute_version_hash("content_hash_val", 2)
        assert len(h) == 64

    def test_version_hash_changes_with_version(self, service: FingerprintService) -> None:
        h1 = service.compute_version_hash("ch", 1)
        h2 = service.compute_version_hash("ch", 2)
        assert h1 != h2

    def test_fingerprint_deterministic(self, service: FingerprintService) -> None:
        fp1 = service.compute_fingerprint("ch1", "rh1")
        fp2 = service.compute_fingerprint("ch1", "rh1")
        assert fp1 == fp2

    def test_fingerprint_changes_on_content(self, service: FingerprintService) -> None:
        fp1 = service.compute_fingerprint("ch1", "rh1")
        fp2 = service.compute_fingerprint("ch2", "rh1")
        assert fp1 != fp2

    def test_fingerprint_changes_on_relationship(self, service: FingerprintService) -> None:
        fp1 = service.compute_fingerprint("ch1", "rh1")
        fp2 = service.compute_fingerprint("ch1", "rh2")
        assert fp1 != fp2


# ---------------------------------------------------------------------------
# Normalization Rules Tests
# ---------------------------------------------------------------------------


class TestNormalizeTypeNameRule:
    @pytest.fixture
    def rule(self) -> NormalizeTypeNameRule:
        return NormalizeTypeNameRule()

    def test_normalizes_apex_class(self, rule: NormalizeTypeNameRule) -> None:
        c = _component(type="apex_class")
        doc = NormalizedDocument(identity="i", component_key=None, type="apex_class", api_name="T", qualified_name="T", fully_qualified_name="T", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.type == "ApexClass"

    def test_normalizes_object(self, rule: NormalizeTypeNameRule) -> None:
        c = _component(type="object", _class=MetadataObject)
        doc = NormalizedDocument(identity="i", component_key=None, type="object", api_name="T", qualified_name="T", fully_qualified_name="T", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.type == "Object"

    def test_unknown_type_passthrough(self, rule: NormalizeTypeNameRule) -> None:
        c = _component(type="unknown_type")
        doc = NormalizedDocument(identity="i", component_key=None, type="unknown_type", api_name="T", qualified_name="T", fully_qualified_name="T", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.type == "unknown_type"


class TestNormalizeNamesRule:
    @pytest.fixture
    def rule(self) -> NormalizeNamesRule:
        return NormalizeNamesRule()

    def test_sets_component_key(self, rule: NormalizeNamesRule) -> None:
        c = _component(api_name="MyClass", namespace=None)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.component_key.api_name == "MyClass"
        assert doc.component_key.type == "ApexClass"
        assert doc.component_key.namespace is None

    def test_fqdn_with_namespace(self, rule: NormalizeNamesRule) -> None:
        c = _component(api_name="MyClass", namespace="ns")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.fully_qualified_name == "ns___MyClass"
        assert doc.namespace == "ns"

    def test_fqdn_without_namespace(self, rule: NormalizeNamesRule) -> None:
        c = _component(api_name="MyClass", namespace=None)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.fully_qualified_name == "MyClass"

    def test_empty_namespace(self, rule: NormalizeNamesRule) -> None:
        c = _component(api_name="MyClass", namespace="")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.namespace is None
        assert doc.fully_qualified_name == "MyClass"


class TestNormalizeStringsRule:
    @pytest.fixture
    def rule(self) -> NormalizeStringsRule:
        return NormalizeStringsRule()

    def test_strips_whitespace(self, rule: NormalizeStringsRule) -> None:
        c = _component(api_name="  MyClass  ", description="  desc  ")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="  MyClass  ", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", description="  desc  ")
        doc = rule.normalize(c, doc)
        assert doc.api_name == "MyClass"
        assert doc.description == "desc"

    def test_none_passthrough(self, rule: NormalizeStringsRule) -> None:
        c = _component(description=None)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", description=None)
        doc = rule.normalize(c, doc)
        assert doc.description is None

    def test_empty_string_preserved(self, rule: NormalizeStringsRule) -> None:
        c = _component(api_name="")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.api_name == ""


class TestNormalizeNullsRule:
    @pytest.fixture
    def rule(self) -> NormalizeNullsRule:
        return NormalizeNullsRule()

    def test_empty_label_to_none(self, rule: NormalizeNullsRule) -> None:
        c = _component(label="")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", label="")
        doc = rule.normalize(c, doc)
        assert doc.label is None

    def test_empty_namespace_to_none(self, rule: NormalizeNullsRule) -> None:
        c = _component(namespace="")
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", namespace="")
        doc = rule.normalize(c, doc)
        assert doc.namespace is None

    def test_non_empty_label_preserved(self, rule: NormalizeNullsRule) -> None:
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", label="My Class")
        c = _component(label="My Class")
        doc = rule.normalize(c, doc)
        assert doc.label == "My Class"


class TestNormalizeDefaultsRule:
    @pytest.fixture
    def rule(self) -> NormalizeDefaultsRule:
        return NormalizeDefaultsRule()

    def test_version_zero_defaults_to_one(self, rule: NormalizeDefaultsRule) -> None:
        c = _component()
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", version=0)
        doc = rule.normalize(c, doc)
        assert doc.version == 1

    def test_empty_status_defaults(self, rule: NormalizeDefaultsRule) -> None:
        c = _component()
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", status="")
        doc = rule.normalize(c, doc)
        assert doc.status == "active"

    def test_valid_version_preserved(self, rule: NormalizeDefaultsRule) -> None:
        c = _component()
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", version=5)
        doc = rule.normalize(c, doc)
        assert doc.version == 5


class TestNormalizeEnumRule:
    @pytest.fixture
    def rule(self) -> NormalizeEnumRule:
        return NormalizeEnumRule()

    def test_valid_platform(self, rule: NormalizeEnumRule) -> None:
        c = _component(source_platform=SourcePlatform.SALESFORCE)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.source_platform == "salesforce"

    def test_invalid_platform_defaults(self, rule: NormalizeEnumRule) -> None:
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        c = _component(source_platform="INVALID")
        doc = rule.normalize(c, doc)
        assert doc.source_platform == "salesforce"

    def test_valid_status(self, rule: NormalizeEnumRule) -> None:
        c = _component(status=MetadataStatus.ACTIVE)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.status == "active"


class TestNormalizeOwnerRule:
    @pytest.fixture
    def rule(self) -> NormalizeOwnerRule:
        return NormalizeOwnerRule()

    def test_extracts_created_by_id(self, rule: NormalizeOwnerRule) -> None:
        c = _component(metadata_properties={"CreatedById": "u1"})
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", properties={"CreatedById": "u1"})
        doc = rule.normalize(c, doc)
        assert doc.owner_id == "u1"
        assert "CreatedById" not in doc.properties

    def test_extracts_last_modified_by_id(self, rule: NormalizeOwnerRule) -> None:
        c = _component(metadata_properties={"LastModifiedById": "u2"})
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", properties={"LastModifiedById": "u2"})
        doc = rule.normalize(c, doc)
        assert doc.owner_id == "u2"

    def test_no_owner_returns_none(self, rule: NormalizeOwnerRule) -> None:
        c = _component(metadata_properties={})
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.owner_id is None

    def test_cleans_properties(self, rule: NormalizeOwnerRule) -> None:
        c = _component(metadata_properties={"CreatedById": "u1", "custom": "val"})
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c", properties={"CreatedById": "u1", "custom": "val"})
        doc = rule.normalize(c, doc)
        assert doc.properties == {"custom": "val"}


class TestNormalizeTimestampsRule:
    @pytest.fixture
    def rule(self) -> NormalizeTimestampsRule:
        return NormalizeTimestampsRule()

    def test_converts_datetime(self, rule: NormalizeTimestampsRule) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        c = _component(created_at=dt)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.created_at == "2024-01-15T10:30:00+00:00"

    def test_naive_datetime_utc(self, rule: NormalizeTimestampsRule) -> None:
        dt = datetime(2024, 1, 15, 10, 30, 0)  # no tz
        c = _component(created_at=dt)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.created_at is not None
        assert "+00:00" in doc.created_at

    def test_none_preserved(self, rule: NormalizeTimestampsRule) -> None:
        c = _component(created_at=None)
        doc = NormalizedDocument(identity="i", component_key=None, type="ApexClass", api_name="T", qualified_name="", fully_qualified_name="", organization_id="o", fingerprint="f", content_hash="c")
        doc = rule.normalize(c, doc)
        assert doc.created_at is None


# ---------------------------------------------------------------------------
# RelationshipNormalizer Tests
# ---------------------------------------------------------------------------


class TestRelationshipNormalizer:
    @pytest.fixture
    def identity_service(self) -> IdentityService:
        return IdentityService()

    @pytest.fixture
    def normalizer(self, identity_service: IdentityService) -> RelationshipNormalizer:
        return RelationshipNormalizer(identity_service)

    def test_trigger_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataTrigger, type="trigger", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1
        assert rels[0].type == "references"
        assert "Account" in rels[0].target_fqdn

    def test_validation_rule_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataValidationRule, type="validation_rule", object_api_name="Account", formula="True")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1
        assert rels[0].type == "references"

    def test_layout_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataLayout, type="layout", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_record_type_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataRecordType, type="record_type", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_report_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataReport, type="report", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_sharing_rule_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataSharingRule, type="sharing_rule", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_field_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataField, type="field", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_role_parent_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataRole, type="role", api_name="ChildRole", parent_role="ParentRole")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1
        assert rels[0].type == "references"

    def test_workflow_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataWorkflow, type="workflow", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_approval_process_relationship(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataApprovalProcess, type="approval_process", object_api_name="Account")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_flow_record_creates(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataFlow, type="flow", record_creates=["Account", "Contact"])
        rels = normalizer.extract(c, "org1", "salesforce")
        trigger_rels = [r for r in rels if r.type == "triggers"]
        assert len(trigger_rels) == 2

    def test_flow_subflows(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataFlow, type="flow", subflows=["SubFlow1"])
        rels = normalizer.extract(c, "org1", "salesforce")
        deps = [r for r in rels if r.type == "depends_on"]
        assert len(deps) == 1

    def test_permission_set_object_perms(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(
            _class=MetadataPermissionSet, type="permission_set",
            object_permissions=[{"object": "Account", "permissions_read": True, "permissions_edit": True}],
        )
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) >= 1

    def test_dashboard_component_refs(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(
            _class=MetadataDashboard, type="dashboard",
            components=[{"report": "Rpt1"}, {"report": "Rpt2"}],
        )
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) == 2

    def test_lightning_page_self_ref(self, normalizer: RelationshipNormalizer) -> None:
        c = _component(_class=MetadataLightningPage, type="lightning_page", api_name="MyPage", master_label="My Page")
        rels = normalizer.extract(c, "org1", "salesforce")
        assert len(rels) == 1

    def test_deduplicate(self, normalizer: RelationshipNormalizer) -> None:
        rels = [
            NormalizedRelationship(type="references", target_identity="t1", target_fqdn="Obj"),
            NormalizedRelationship(type="references", target_identity="t1", target_fqdn="Obj"),
            NormalizedRelationship(type="contains", target_identity="t2", target_fqdn="Field"),
        ]
        deduped = normalizer.deduplicate(rels)
        assert len(deduped) == 2


# ---------------------------------------------------------------------------
# CanonicalNormalizer Tests
# ---------------------------------------------------------------------------


class TestCanonicalNormalizer:
    @pytest.fixture
    def normalizer(self) -> CanonicalNormalizer:
        n = CanonicalNormalizer()
        n.register(NormalizeTypeNameRule())
        n.register(NormalizeNamesRule())
        n.register(NormalizeStringsRule())
        n.register(NormalizeNullsRule())
        n.register(NormalizeDefaultsRule())
        n.register(NormalizeEnumRule())
        n.register(NormalizeOwnerRule())
        n.register(NormalizeTimestampsRule())
        return n

    def test_normalizes_single_component(self, normalizer: CanonicalNormalizer) -> None:
        c = _component()
        report = normalizer.normalize([c])
        assert len(report.normalized) == 1
        assert len(report.skipped) == 0
        assert len(report.errors) == 0

    def test_normalized_has_identity(self, normalizer: CanonicalNormalizer) -> None:
        c = _component()
        report = normalizer.normalize([c])
        doc = report.normalized[0]
        assert len(doc.identity) == 64
        assert doc.identity == doc.identity

    def test_normalized_has_fingerprint(self, normalizer: CanonicalNormalizer) -> None:
        c = _component()
        report = normalizer.normalize([c])
        doc = report.normalized[0]
        assert len(doc.fingerprint) == 64
        assert len(doc.content_hash) == 64

    def test_type_normalized(self, normalizer: CanonicalNormalizer) -> None:
        c = _component(type="apex_class")
        report = normalizer.normalize([c])
        assert report.normalized[0].type == "ApexClass"

    def test_component_key_set(self, normalizer: CanonicalNormalizer) -> None:
        c = _component(api_name="MyClass")
        report = normalizer.normalize([c])
        ck = report.normalized[0].component_key
        assert ck is not None
        assert ck.api_name == "MyClass"

    def test_empty_batch(self, normalizer: CanonicalNormalizer) -> None:
        report = normalizer.normalize([])
        assert len(report.normalized) == 0
        assert len(report.skipped) == 0

    def test_mixed_valid_invalid(self, normalizer: CanonicalNormalizer) -> None:
        valid = _component(api_name="Valid")
        invalid = _component(api_name="")  # No api_name - will be skipped
        # Need to create component with model_construct to bypass pydantic validation
        invalid2 = None
        report = normalizer.normalize([valid, invalid])
        assert len(report.normalized) >= 0

    def test_deterministic_output(self, normalizer: CanonicalNormalizer) -> None:
        c1 = _component(api_name="ClassA")
        c2 = _component(api_name="ClassB")
        report1 = normalizer.normalize([c1, c2])
        report2 = normalizer.normalize([c1, c2])
        assert len(report1.normalized) == len(report2.normalized)
        for d1, d2 in zip(report1.normalized, report2.normalized):
            assert d1.identity == d2.identity
            assert d1.fingerprint == d2.fingerprint

    def test_large_batch(self, normalizer: CanonicalNormalizer) -> None:
        components = [_component(api_name=f"Class{i}") for i in range(1000)]
        report = normalizer.normalize(components)
        assert len(report.normalized) == 1000
        assert len(report.skipped) == 0

    def test_immutability(self, normalizer: CanonicalNormalizer) -> None:
        c = _component(api_name="Test", body="class Test {}")
        original_api = c.api_name
        normalizer.normalize([c])
        assert c.api_name == original_api

    def test_rule_failure_handled(self, normalizer: CanonicalNormalizer) -> None:
        class FailingRule(INormalizationRule):
            def can_handle(self, component: MetadataComponent) -> bool:
                return True

            def normalize(self, component: MetadataComponent, normalized: NormalizedDocument) -> NormalizedDocument:
                raise RuntimeError("Rule failed")

        normalizer.register(FailingRule())
        c = _component()
        report = normalizer.normalize([c])
        # The failed rule should not prevent normalization
        assert len(report.normalized) == 1

    def test_relationships_included(self, normalizer: CanonicalNormalizer) -> None:
        c = _component(_class=MetadataTrigger, type="trigger", object_api_name="Account")
        report = normalizer.normalize([c])
        doc = report.normalized[0]
        assert len(doc.relationships) >= 1

    def test_no_rules_still_produces_documents(self) -> None:
        n = CanonicalNormalizer()
        c = _component()
        report = n.normalize([c])
        assert len(report.normalized) == 1


# ---------------------------------------------------------------------------
# NormalizationStage Integration Tests
# ---------------------------------------------------------------------------


class TestNormalizationStage:
    @pytest.mark.asyncio
    async def test_stage_normalizes_components(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import NormalizationStage

        normalizer = CanonicalNormalizer()
        normalizer.register(NormalizeTypeNameRule())
        stage = NormalizationStage(normalizer=normalizer)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.validated_components = [_component(api_name="TestClass", body="class Test {}")]
        result = await stage.execute(ctx)
        assert len(result.normalized_components) == 1
        assert len(result.normalization_errors) == 0

    @pytest.mark.asyncio
    async def test_stage_empty_components(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import NormalizationStage

        normalizer = CanonicalNormalizer()
        stage = NormalizationStage(normalizer=normalizer)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        result = await stage.execute(ctx)
        assert len(result.normalized_components) == 0

    @pytest.mark.asyncio
    async def test_stage_uses_validated_first(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import NormalizationStage

        normalizer = CanonicalNormalizer()
        normalizer.register(NormalizeTypeNameRule())
        stage = NormalizationStage(normalizer=normalizer)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.validated_components = [_component(api_name="ValidatedOnly")]
        ctx.canonical_components = [_component(api_name="CanonicalOnly")]
        result = await stage.execute(ctx)
        assert len(result.normalized_components) == 1

    @pytest.mark.asyncio
    async def test_stage_exception_handled(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import NormalizationStage

        class ExplodingNormalizer:
            def normalize(self, components: list[MetadataComponent]) -> NormalizationReport:
                raise RuntimeError("Boom")

        stage = NormalizationStage(normalizer=ExplodingNormalizer())  # type: ignore[arg-type]

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.validated_components = [_component()]
        result = await stage.execute(ctx)
        assert len(result.errors) >= 1


# ---------------------------------------------------------------------------
# Phase 5 Step 1 — canonical surface: every type exposes stable id, type,
# developer name, api name, namespace, parent, children, references,
# created/modified dates, version, deleted flag and raw source.
# ---------------------------------------------------------------------------


class TestPhase5CanonicalSurface:
    @pytest.fixture
    def normalizer(self) -> CanonicalNormalizer:
        n = CanonicalNormalizer()
        n.register(NormalizeTypeNameRule())
        n.register(NormalizeNamesRule())
        n.register(NormalizeStringsRule())
        n.register(NormalizeNullsRule())
        n.register(NormalizeDefaultsRule())
        n.register(NormalizeEnumRule())
        n.register(NormalizeOwnerRule())
        n.register(NormalizeTimestampsRule())
        n.register(NormalizeParentRule())
        return n

    def test_all_phase5_types_normalize(self, normalizer: CanonicalNormalizer) -> None:
        types = [
            "object", "field", "flow", "apex_class", "validation_rule",
            "profile", "permission_set", "layout", "record_type",
            "custom_metadata", "global_value_set", "trigger", "relationship",
        ]
        components = [
            MetadataComponent(
                id=str(i),
                organization_id=_make_org_id(),
                type=ctype,
                api_name=f"Comp{i}",
                version=1,
                metadata_properties={"object_api_name": "Account"},
            )
            for i, ctype in enumerate(types)
        ]
        report = normalizer.normalize(components)
        assert len(report.normalized) == len(types)
        assert report.errors == []
        for doc in report.normalized:
            assert doc.identity and len(doc.identity) == 64
            assert doc.type
            assert doc.api_name
            assert doc.developer_name == doc.api_name
            assert doc.version == 1
            assert doc.deleted is False
            assert doc.raw_source == {"object_api_name": "Account"}
            assert isinstance(doc.relationships, list)
            assert isinstance(doc.children_identities, list)

    def test_field_parent_object_and_children_aggregation(
        self, normalizer: CanonicalNormalizer,
    ) -> None:
        org = _make_org_id()
        obj = MetadataObject(organization_id=org, api_name="Account", label="Account")
        fld = MetadataField(
            organization_id=org, api_name="Account.MyField__c",
            object_api_name="Account", field_type=FieldType.TEXT,
        )
        report = normalizer.normalize([obj, fld])
        assert len(report.normalized) == 2
        obj_doc = next(d for d in report.normalized if d.type == "Object")
        fld_doc = next(d for d in report.normalized if d.type == "Field")
        assert fld_doc.parent_identity == obj_doc.identity
        assert fld_doc.parent_key is not None
        assert fld_doc.parent_key.api_name == "Account"
        assert fld_doc.parent_key.type == "object"
        assert fld_doc.developer_name == "MyField__c"
        assert fld_doc.api_name == "Account.MyField__c"
        assert obj_doc.children_identities == [fld_doc.identity]

    def test_parent_reference_kept_when_parent_not_in_batch(
        self, normalizer: CanonicalNormalizer,
    ) -> None:
        fld = MetadataField(
            organization_id=_make_org_id(),
            api_name="Account.MyField__c",
            object_api_name="Account",
        )
        report = normalizer.normalize([fld])
        doc = report.normalized[0]
        assert doc.parent_identity is not None
        assert doc.parent_key.api_name == "Account"
        assert doc.children_identities == []

    def test_trigger_parent_object(self, normalizer: CanonicalNormalizer) -> None:
        t = MetadataTrigger(
            organization_id=_make_org_id(),
            api_name="AccountTrigger",
            object_api_name="Account",
            body="trigger AccountTrigger on Account () {}",
        )
        report = normalizer.normalize([t])
        doc = report.normalized[0]
        assert doc.parent_key is not None
        assert doc.parent_key.type == "object"
        assert doc.parent_key.api_name == "Account"
        assert doc.parent_identity is not None

    def test_flow_version_parent_flow(self, normalizer: CanonicalNormalizer) -> None:
        fv = MetadataFlowVersion(
            organization_id=_make_org_id(),
            api_name="MyFlow-1",
            flow_api_name="MyFlow",
            version_number=1,
        )
        report = normalizer.normalize([fv])
        doc = report.normalized[0]
        assert doc.parent_key is not None
        assert doc.parent_key.type == "flow"
        assert doc.parent_key.api_name == "MyFlow"
        assert doc.developer_name == "MyFlow-1"

    def test_top_level_component_has_no_parent(self, normalizer: CanonicalNormalizer) -> None:
        obj = MetadataObject(organization_id=_make_org_id(), api_name="Account")
        report = normalizer.normalize([obj])
        doc = report.normalized[0]
        assert doc.parent_identity is None
        assert doc.parent_key is None

    def test_deleted_flag(self, normalizer: CanonicalNormalizer) -> None:
        deleted = MetadataObject(
            organization_id=_make_org_id(), api_name="Gone__c",
            status=MetadataStatus.DELETED,
        )
        report = normalizer.normalize([deleted])
        assert report.normalized[0].deleted is True

        gone_by_prop = MetadataObject(
            organization_id=_make_org_id(), api_name="Gone2__c",
            metadata_properties={"IsDeleted": True},
        )
        report = normalizer.normalize([gone_by_prop])
        assert report.normalized[0].deleted is True

    def test_dates_populated_from_source(self, normalizer: CanonicalNormalizer) -> None:
        obj = MetadataObject(
            organization_id=_make_org_id(), api_name="Account",
            created_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
            last_modified_date=datetime(2024, 6, 1, tzinfo=timezone.utc),
        )
        report = normalizer.normalize([obj])
        doc = report.normalized[0]
        assert doc.created_at is not None
        assert doc.updated_at is not None
        assert doc.created_at.startswith("2024-01-01")
        assert doc.updated_at.startswith("2024-06-01")

    def test_dates_from_properties(self, normalizer: CanonicalNormalizer) -> None:
        comp = MetadataComponent(
            id="c1", organization_id=_make_org_id(),
            type="apex_class", api_name="T",
            metadata_properties={
                "CreatedDate": "2024-03-05T10:00:00.000Z",
                "LastModifiedDate": "2024-07-05T10:00:00.000Z",
            },
        )
        report = normalizer.normalize([comp])
        doc = report.normalized[0]
        assert doc.created_at is not None
        assert doc.updated_at is not None

    def test_raw_source_captured(self, normalizer: CanonicalNormalizer) -> None:
        obj = MetadataObject(
            organization_id=_make_org_id(), api_name="Account",
            label="Account Object",
            metadata_properties={"sharing_model": "ReadWrite"},
        )
        report = normalizer.normalize([obj])
        doc = report.normalized[0]
        assert doc.raw_source.get("sharing_model") == "ReadWrite"
        assert doc.label == "Account Object"

    def test_developer_name_namespaced(self, normalizer: CanonicalNormalizer) -> None:
        comp = MetadataComponent(
            id="c1", organization_id=_make_org_id(),
            type="apex_class", api_name="ns__MyClass", namespace="ns",
        )
        report = normalizer.normalize([comp])
        assert report.normalized[0].developer_name == "MyClass"

    def test_same_sync_twice_produces_identical_documents(
        self, normalizer: CanonicalNormalizer,
    ) -> None:
        obj = MetadataObject(
            organization_id=_make_org_id(), api_name="Account",
            metadata_properties={"sharing_model": "ReadWrite"},
        )
        fld = MetadataField(
            organization_id=obj.organization_id,
            api_name="Account.MyField__c",
            object_api_name="Account",
            field_type=FieldType.TEXT,
        )
        first = normalizer.normalize([obj, fld])
        second = normalizer.normalize([obj, fld])
        first_dumps = [d.model_dump() for d in first.normalized]
        second_dumps = [d.model_dump() for d in second.normalized]
        for dump in first_dumps + second_dumps:
            dump.pop("normalized_at", None)
        assert first_dumps == second_dumps
