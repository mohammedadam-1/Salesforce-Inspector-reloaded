"""Tests for canonical metadata models.

Covers: construction, inheritance, serialization, validation, enums,
backward compatibility, and relationship modeling.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from sfir_backend.domain.canonical import (
    CanonicalRelationship,
    FieldType,
    MetadataApexClass,
    MetadataApprovalProcess,
    MetadataComponent,
    MetadataConnectedApp,
    MetadataCustomMetadata,
    MetadataCustomSetting,
    MetadataDashboard,
    MetadataEmailTemplate,
    MetadataField,
    MetadataFlow,
    MetadataFlowVersion,
    MetadataFormula,
    MetadataGlobalValueSet,
    MetadataLayout,
    MetadataLightningPage,
    MetadataNamedCredential,
    MetadataObject,
    MetadataPermissionSet,
    MetadataProfile,
    MetadataPublicGroup,
    MetadataQueue,
    MetadataQuickAction,
    MetadataRecordType,
    MetadataRelationship,
    MetadataReport,
    MetadataRole,
    MetadataSharingRule,
    MetadataStatus,
    MetadataTrigger,
    MetadataValidationRule,
    MetadataWorkflow,
    RelationshipType,
    SourcePlatform,
)

# ─── Enums ──────────────────────────────────────────────────────

class TestEnums:
    def test_source_platform_values(self) -> None:
        assert SourcePlatform.SALESFORCE.value == "salesforce"
        assert SourcePlatform.SERVICENOW.value == "servicenow"
        assert SourcePlatform.HUBSPOT.value == "hubspot"
        assert SourcePlatform.SAP.value == "sap"
        assert SourcePlatform.DYNAMICS.value == "dynamics"
        assert SourcePlatform.GITHUB.value == "github"
        assert SourcePlatform.GITLAB.value == "gitlab"
        assert SourcePlatform.AZURE_DEVOPS.value == "azure_devops"

    def test_metadata_status_values(self) -> None:
        assert MetadataStatus.ACTIVE.value == "active"
        assert MetadataStatus.INACTIVE.value == "inactive"
        assert MetadataStatus.DELETED.value == "deleted"
        assert MetadataStatus.DEPRECATED.value == "deprecated"
        assert MetadataStatus.DRAFT.value == "draft"

    def test_relationship_type_values(self) -> None:
        assert RelationshipType.CONTAINS.value == "contains"
        assert RelationshipType.REFERENCES.value == "references"
        assert RelationshipType.DEPENDS_ON.value == "depends_on"

    def test_field_type_values(self) -> None:
        assert FieldType.TEXT.value == "text"
        assert FieldType.NUMBER.value == "number"
        assert FieldType.FORMULA.value == "formula"
        assert FieldType.LOOKUP.value == "lookup"


# ─── Base & Relationship ───────────────────────────────────────

class TestMetadataComponent:
    def test_default_construction(self) -> None:
        comp = MetadataComponent()
        assert comp.id == ""
        assert comp.organization_id == ""
        assert comp.type == ""
        assert comp.api_name == ""
        assert comp.source_platform == SourcePlatform.SALESFORCE
        assert comp.status == MetadataStatus.ACTIVE
        assert comp.version == 1
        assert comp.relationships == []
        assert comp.metadata_properties == {}

    def test_full_construction(self) -> None:
        now = datetime.now(tz=UTC)
        comp = MetadataComponent(
            id="cmp-1",
            organization_id="org-1",
            type="custom_type",
            api_name="MyComponent",
            label="My Component",
            namespace="ns",
            description="A test component",
            version=3,
            created_at=now,
            updated_at=now,
            source_platform=SourcePlatform.HUBSPOT,
            hash="abc123",
            status=MetadataStatus.DRAFT,
            relationships=[
                CanonicalRelationship(
                    type=RelationshipType.REFERENCES,
                    target_type="object",
                    target_api_name="Account",
                ),
            ],
            metadata_properties={"key": "value"},
        )
        assert comp.id == "cmp-1"
        assert comp.organization_id == "org-1"
        assert comp.type == "custom_type"
        assert comp.api_name == "MyComponent"
        assert comp.label == "My Component"
        assert comp.namespace == "ns"
        assert comp.description == "A test component"
        assert comp.version == 3
        assert comp.created_at == now
        assert comp.updated_at == now
        assert comp.source_platform == SourcePlatform.HUBSPOT
        assert comp.hash == "abc123"
        assert comp.status == MetadataStatus.DRAFT
        assert len(comp.relationships) == 1
        assert comp.metadata_properties["key"] == "value"

    def test_serialization_roundtrip(self) -> None:
        comp = MetadataComponent(api_name="Roundtrip", type="test")
        data = comp.model_dump()
        restored = MetadataComponent.model_validate(data)
        assert restored.api_name == "Roundtrip"
        assert restored.model_dump() == data

    def test_json_serialization(self) -> None:
        comp = MetadataComponent(api_name="JsonTest")
        json_str = comp.model_dump_json()
        restored = MetadataComponent.model_validate_json(json_str)
        assert restored.api_name == "JsonTest"


class TestCanonicalRelationship:
    def test_defaults(self) -> None:
        rel = CanonicalRelationship(target_type="object", target_api_name="Account")
        assert rel.type == RelationshipType.REFERENCES
        assert rel.target_type == "object"
        assert rel.target_api_name == "Account"
        assert rel.source_platform == SourcePlatform.SALESFORCE
        assert rel.metadata == {}

    def test_full_construction(self) -> None:
        rel = CanonicalRelationship(
            type=RelationshipType.DEPENDS_ON,
            target_type="field",
            target_api_name="Account.Name",
            target_label="Account Name",
            source_platform=SourcePlatform.SERVICENOW,
            metadata={"critical": True},
        )
        assert rel.type == RelationshipType.DEPENDS_ON
        assert rel.target_api_name == "Account.Name"
        assert rel.metadata["critical"] is True


# ─── Concrete Models ────────────────────────────────────────────

class SharedAssertions:
    """Mixin-like helpers for model construction tests."""

    @staticmethod
    def assert_defaults(obj: MetadataComponent, expected_type: str) -> None:
        assert obj.type == expected_type
        assert obj.api_name == ""
        assert obj.id == ""
        assert obj.status == MetadataStatus.ACTIVE
        assert obj.source_platform == SourcePlatform.SALESFORCE
        assert isinstance(obj.relationships, list)
        assert isinstance(obj.metadata_properties, dict)

    @staticmethod
    def assert_serialization(obj: MetadataComponent) -> None:
        data = obj.model_dump()
        restored = obj.__class__.model_validate(data)
        assert restored.model_dump() == data


class TestMetadataField:
    def test_defaults(self) -> None:
        f = MetadataField()
        SharedAssertions.assert_defaults(f, "field")
        assert f.object_api_name == ""
        assert f.field_type == FieldType.TEXT
        assert f.required is False
        assert f.unique is False

    def test_full(self) -> None:
        f = MetadataField(
            api_name="MyField__c",
            label="My Field",
            object_api_name="MyObject__c",
            field_type=FieldType.CURRENCY,
            length=10,
            precision=12,
            scale=2,
            required=True,
            unique=True,
            external_id=True,
            default_value="0",
            picklist_values=[{"label": "A", "value": "a"}],
            relationship_name="MyRel",
            reference_to="OtherObject__c",
            cascade_delete=True,
            formula="FIELD1 + FIELD2",
            help_text="Help",
            tracked_history=True,
        )
        assert f.api_name == "MyField__c"
        assert f.field_type == FieldType.CURRENCY
        assert f.length == 10
        assert f.required is True
        assert f.formula == "FIELD1 + FIELD2"
        SharedAssertions.assert_serialization(f)

    def test_validation_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            MetadataField(field_type="invalid_type")

    def test_inherits_base(self) -> None:
        assert isinstance(MetadataField(), MetadataComponent)


class TestMetadataObject:
    def test_defaults(self) -> None:
        obj = MetadataObject()
        SharedAssertions.assert_defaults(obj, "object")
        assert obj.plural_label == ""
        assert obj.sharing_model == "ReadWrite"
        assert obj.fields == []

    def test_full(self) -> None:
        obj = MetadataObject(
            api_name="CustomObject__c",
            label="Custom Object",
            plural_label="Custom Objects",
            enable_reports=True,
            enable_search=True,
            fields=[
                MetadataField(api_name="Field1__c", label="Field 1"),
                MetadataField(api_name="Field2__c", label="Field 2"),
            ],
        )
        assert len(obj.fields) == 2
        assert obj.fields[0].api_name == "Field1__c"
        SharedAssertions.assert_serialization(obj)

    def test_inherits_base(self) -> None:
        assert isinstance(MetadataObject(), MetadataComponent)


class TestMetadataRelationship:
    def test_defaults(self) -> None:
        r = MetadataRelationship()
        SharedAssertions.assert_defaults(r, "relationship")
        assert r.source_api_name == ""
        assert r.relationship_type == "lookup"

    def test_full(self) -> None:
        r = MetadataRelationship(
            api_name="Account_Owner_Rel",
            source_api_name="Account",
            target_api_name="User",
            relationship_type="master_detail",
            cascade_delete=True,
        )
        assert r.source_api_name == "Account"
        assert r.target_api_name == "User"
        assert r.cascade_delete is True
        SharedAssertions.assert_serialization(r)


class TestMetadataGlobalValueSet:
    def test_defaults(self) -> None:
        gvs = MetadataGlobalValueSet()
        SharedAssertions.assert_defaults(gvs, "global_value_set")
        assert gvs.custom_value == []

    def test_full(self) -> None:
        gvs = MetadataGlobalValueSet(
            api_name="Industry",
            master_label="Industry",
            custom_value=[{"label": "Tech", "value": "Tech"}],
            grouped=True,
            sorting_order="Alphabetical",
        )
        assert gvs.master_label == "Industry"
        assert gvs.grouped is True
        SharedAssertions.assert_serialization(gvs)


class TestMetadataApexClass:
    def test_defaults(self) -> None:
        cls_ = MetadataApexClass()
        SharedAssertions.assert_defaults(cls_, "apex_class")
        assert cls_.body == ""

    def test_full(self) -> None:
        cls_ = MetadataApexClass(
            api_name="MyController",
            body="public class MyController {}",
            api_version=62,
            status="active",
            package_versions=[{"namespace": "sf", "version": 62.0}],
            urls=["/services/data/v62.0/"],
        )
        assert cls_.body == "public class MyController {}"
        SharedAssertions.assert_serialization(cls_)


class TestMetadataTrigger:
    def test_defaults(self) -> None:
        t = MetadataTrigger()
        SharedAssertions.assert_defaults(t, "trigger")
        assert t.object_api_name == ""
        assert t.trigger_events == []

    def test_full(self) -> None:
        t = MetadataTrigger(
            api_name="AccountTrigger",
            object_api_name="Account",
            trigger_events=["before insert", "after insert"],
            usage_before_insert=True,
            usage_after_insert=True,
        )
        assert t.object_api_name == "Account"
        assert len(t.trigger_events) == 2
        SharedAssertions.assert_serialization(t)


class TestMetadataFlow:
    def test_defaults(self) -> None:
        flow = MetadataFlow()
        SharedAssertions.assert_defaults(flow, "flow")
        assert flow.process_type == "Flow"
        assert flow.flow_status == MetadataStatus.DRAFT

    def test_full(self) -> None:
        flow = MetadataFlow(
            api_name="MyFlow",
            process_type="Workflow",
            flow_status="active",
            variables=[{"name": "var1", "data_type": "String"}],
            subflows=["SubFlow1"],
        )
        assert len(flow.variables) == 1
        assert flow.subflows == ["SubFlow1"]
        SharedAssertions.assert_serialization(flow)

    def test_with_versions(self) -> None:
        flow = MetadataFlow(
            api_name="FlowWithVersions",
            versions=[
                MetadataFlowVersion(api_name="v1", version_number=1, status="draft"),
                MetadataFlowVersion(api_name="v2", version_number=2, status="active"),
            ],
        )
        assert len(flow.versions) == 2
        assert flow.versions[1].status == MetadataStatus.ACTIVE


class TestMetadataFlowVersion:
    def test_defaults(self) -> None:
        fv = MetadataFlowVersion()
        SharedAssertions.assert_defaults(fv, "flow_version")
        assert fv.flow_api_name == ""
        assert fv.version_number == 1

    def test_full(self) -> None:
        fv = MetadataFlowVersion(
            api_name="MyFlow_v3",
            flow_api_name="MyFlow",
            version_number=3,
            definition={"elements": []},
        )
        assert fv.flow_api_name == "MyFlow"
        assert fv.definition["elements"] == []


class TestMetadataValidationRule:
    def test_defaults(self) -> None:
        vr = MetadataValidationRule()
        SharedAssertions.assert_defaults(vr, "validation_rule")
        assert vr.object_api_name == ""
        assert vr.active is True

    def test_full(self) -> None:
        vr = MetadataValidationRule(
            api_name="MyValidationRule",
            object_api_name="Account",
            active=True,
            error_message="Error!",
            formula="Age < 18",
        )
        assert vr.formula == "Age < 18"
        SharedAssertions.assert_serialization(vr)


class TestMetadataFormula:
    def test_defaults(self) -> None:
        f = MetadataFormula()
        SharedAssertions.assert_defaults(f, "formula")
        assert f.formula_expression == ""

    def test_full(self) -> None:
        f = MetadataFormula(
            api_name="FullNameFormula",
            object_api_name="Contact",
            formula_expression="FirstName & ' ' & LastName",
            return_type="Text",
        )
        assert f.return_type == "Text"


class TestMetadataLayout:
    def test_defaults(self) -> None:
        l_ = MetadataLayout()
        SharedAssertions.assert_defaults(l_, "layout")
        assert l_.layout_type == "Detail"

    def test_full(self) -> None:
        l_ = MetadataLayout(
            api_name="Account-Layout",
            object_api_name="Account",
            sections=[{"label": "System", "columns": 2}],
            related_lists=[{"related_list": "Contacts"}],
        )
        assert len(l_.sections) == 1
        SharedAssertions.assert_serialization(l_)


class TestMetadataRecordType:
    def test_defaults(self) -> None:
        rt = MetadataRecordType()
        SharedAssertions.assert_defaults(rt, "record_type")
        assert rt.active is True

    def test_full(self) -> None:
        rt = MetadataRecordType(
            api_name="Account.Prospect",
            object_api_name="Account",
            active=True,
            business_process="Prospecting",
        )
        assert rt.business_process == "Prospecting"


class TestMetadataPermissionSet:
    def test_defaults(self) -> None:
        ps = MetadataPermissionSet()
        SharedAssertions.assert_defaults(ps, "permission_set")
        assert ps.user_license == ""

    def test_full(self) -> None:
        ps = MetadataPermissionSet(
            api_name="SalesUser",
            label="Sales User Permissions",
            user_license="Salesforce",
            has_activation=True,
            object_permissions=[{"object_name": "Account", "allow_read": True}],
            field_permissions=[{"object_name": "Account", "field_name": "Name", "readable": True}],
        )
        assert len(ps.object_permissions) == 1


class TestMetadataProfile:
    def test_defaults(self) -> None:
        p = MetadataProfile()
        SharedAssertions.assert_defaults(p, "profile")
        assert p.custom is False

    def test_full(self) -> None:
        p = MetadataProfile(
            api_name="Admin",
            user_license="Salesforce",
            custom=True,
            object_permissions=[{"object_name": "Account", "allow_read": True}],
        )
        assert p.custom is True
        assert len(p.object_permissions) == 1


class TestMetadataReport:
    def test_defaults(self) -> None:
        r = MetadataReport()
        SharedAssertions.assert_defaults(r, "report")
        assert r.report_type == "Tabular"

    def test_full(self) -> None:
        r = MetadataReport(
            api_name="AccountListReport",
            object_api_name="Account",
            report_type="Summary",
            folder_name="Shared Reports",
            params={"grouping": "Type"},
        )
        assert r.params["grouping"] == "Type"


class TestMetadataDashboard:
    def test_defaults(self) -> None:
        d = MetadataDashboard()
        SharedAssertions.assert_defaults(d, "dashboard")
        assert d.background_fitness == "None"

    def test_full(self) -> None:
        d = MetadataDashboard(
            api_name="ExecutiveDashboard",
            dashboard_type="Specified",
            components=[{"type": "chart", "label": "Revenue"}],
        )
        assert len(d.components) == 1


class TestMetadataWorkflow:
    def test_defaults(self) -> None:
        w = MetadataWorkflow()
        SharedAssertions.assert_defaults(w, "workflow")
        assert w.active is True
        assert w.evaluation_criteria == "Everytime"

    def test_full(self) -> None:
        w = MetadataWorkflow(
            api_name="AccountWF",
            object_api_name="Account",
            formula_criteria="Active__c = true",
            actions=[{"type": "field_update", "field": "Status"}],
        )
        assert w.formula_criteria == "Active__c = true"


class TestMetadataApprovalProcess:
    def test_defaults(self) -> None:
        ap = MetadataApprovalProcess()
        SharedAssertions.assert_defaults(ap, "approval_process")
        assert ap.allow_sequential is True

    def test_full(self) -> None:
        ap = MetadataApprovalProcess(
            api_name="ExpenseApproval",
            object_api_name="Expense__c",
            record_editability="ReadOnly",
            steps=[{"name": "Manager Approval", "order": 1}],
        )
        assert ap.record_editability == "ReadOnly"


class TestMetadataCustomMetadata:
    def test_defaults(self) -> None:
        cm = MetadataCustomMetadata()
        SharedAssertions.assert_defaults(cm, "custom_metadata")
        assert cm.visibility == "Public"

    def test_full(self) -> None:
        cm = MetadataCustomMetadata(
            api_name="CountryCodes",
            visibility="Public",
            fields=[{"name": "Code", "type": "Text"}],
        )
        assert len(cm.fields) == 1


class TestMetadataCustomSetting:
    def test_defaults(self) -> None:
        cs = MetadataCustomSetting()
        SharedAssertions.assert_defaults(cs, "custom_setting")
        assert cs.setting_type == "list"

    def test_full(self) -> None:
        cs = MetadataCustomSetting(
            api_name="AppConfig",
            setting_type="hierarchy",
            visibility="Protected",
            fields=[{"name": "Key", "type": "Text"}],
        )
        assert cs.setting_type == "hierarchy"


class TestMetadataLightningPage:
    def test_defaults(self) -> None:
        lp = MetadataLightningPage()
        SharedAssertions.assert_defaults(lp, "lightning_page")
        assert lp.master_label == ""
        assert lp.page_type == "RecordPage"

    def test_full(self) -> None:
        lp = MetadataLightningPage(
            api_name="MyCustomPage",
            master_label="My Custom Page",
            page_type="HomePage",
            regions=[{"name": "main", "components": []}],
        )
        assert lp.master_label == "My Custom Page"


class TestMetadataQuickAction:
    def test_defaults(self) -> None:
        qa = MetadataQuickAction()
        SharedAssertions.assert_defaults(qa, "quick_action")
        assert qa.action_type == "Create"

    def test_full(self) -> None:
        qa = MetadataQuickAction(
            api_name="Account.NewTask",
            object_api_name="Account",
            action_type="Create",
            target_object="Task",
            icon="action:new_task",
            options_create=True,
        )
        assert qa.target_object == "Task"


class TestMetadataEmailTemplate:
    def test_defaults(self) -> None:
        et = MetadataEmailTemplate()
        SharedAssertions.assert_defaults(et, "email_template")
        assert et.template_type == "text"

    def test_full(self) -> None:
        et = MetadataEmailTemplate(
            api_name="WelcomeEmail",
            template_type="html",
            subject="Welcome!",
            content="<h1>Welcome</h1>",
            object_type="Contact",
        )
        assert et.subject == "Welcome!"


class TestMetadataNamedCredential:
    def test_defaults(self) -> None:
        nc = MetadataNamedCredential()
        SharedAssertions.assert_defaults(nc, "named_credential")
        assert nc.endpoint == ""
        assert nc.protocol == "NoAuthentication"

    def test_full(self) -> None:
        nc = MetadataNamedCredential(
            api_name="ExternalAPI",
            endpoint="https://api.example.com",
            principal_type="NamedUser",
            protocol="BasicAuthentication",
            auth_provider="MyProvider",
        )
        assert nc.endpoint == "https://api.example.com"


class TestMetadataConnectedApp:
    def test_defaults(self) -> None:
        ca = MetadataConnectedApp()
        SharedAssertions.assert_defaults(ca, "connected_app")
        assert ca.contact_email == ""
        assert ca.version == "1.0"

    def test_full(self) -> None:
        ca = MetadataConnectedApp(
            api_name="MyApp",
            contact_email="admin@example.com",
            version="2.0",
            oauth_config={"scopes": ["api"]},
            permissions=[{"name": "api_access"}],
            start_url="https://example.com/start",
        )
        assert ca.contact_email == "admin@example.com"


class TestMetadataRole:
    def test_defaults(self) -> None:
        r = MetadataRole()
        SharedAssertions.assert_defaults(r, "role")
        assert r.parent_role is None
        assert r.case_access_level == "None"

    def test_full(self) -> None:
        r = MetadataRole(
            api_name="CEO",
            parent_role="CFO",
            case_access_level="Read",
            opportunity_access_level="Edit",
            may_forecast_manager=True,
        )
        assert r.parent_role == "CFO"


class TestMetadataQueue:
    def test_defaults(self) -> None:
        q = MetadataQueue()
        SharedAssertions.assert_defaults(q, "queue")
        assert q.email is None

    def test_full(self) -> None:
        q = MetadataQueue(
            api_name="SupportQueue",
            email="support-queue@example.com",
            queue_sobjects=[{"object_name": "Case"}],
            queue_members=[{"user_or_group": "Support Team"}],
        )
        assert q.email == "support-queue@example.com"


class TestMetadataPublicGroup:
    def test_defaults(self) -> None:
        pg = MetadataPublicGroup()
        SharedAssertions.assert_defaults(pg, "public_group")
        assert pg.members == []

    def test_full(self) -> None:
        pg = MetadataPublicGroup(
            api_name="AllEmployees",
            members=[{"type": "user", "name": "user@example.com"}],
        )
        assert len(pg.members) == 1


class TestMetadataSharingRule:
    def test_defaults(self) -> None:
        sr = MetadataSharingRule()
        SharedAssertions.assert_defaults(sr, "sharing_rule")
        assert sr.access_level == "Read"
        assert sr.rule_type == "CriteriaBased"

    def test_full(self) -> None:
        sr = MetadataSharingRule(
            api_name="AccountSharing",
            object_api_name="Account",
            shared_to="AllInternalUsers",
            shared_from="SalesTeam",
            access_level="Edit",
            rule_type="CriteriaBased",
        )
        assert sr.shared_to == "AllInternalUsers"


# ─── Inheritance & Category Tests ──────────────────────────────

class TestInheritance:
    ALL_MODELS: tuple[type[MetadataComponent], ...] = (
        MetadataApexClass,
        MetadataApprovalProcess,
        MetadataConnectedApp,
        MetadataCustomMetadata,
        MetadataCustomSetting,
        MetadataDashboard,
        MetadataEmailTemplate,
        MetadataField,
        MetadataFlow,
        MetadataFlowVersion,
        MetadataFormula,
        MetadataGlobalValueSet,
        MetadataLayout,
        MetadataLightningPage,
        MetadataNamedCredential,
        MetadataObject,
        MetadataPermissionSet,
        MetadataProfile,
        MetadataPublicGroup,
        MetadataQueue,
        MetadataQuickAction,
        MetadataRecordType,
        MetadataRelationship,
        MetadataReport,
        MetadataRole,
        MetadataSharingRule,
        MetadataTrigger,
        MetadataValidationRule,
        MetadataWorkflow,
    )

    @pytest.mark.parametrize("model_cls", ALL_MODELS)
    def test_all_inherit_metadata_component(self, model_cls: type) -> None:
        assert issubclass(model_cls, MetadataComponent)

    @pytest.mark.parametrize("model_cls", ALL_MODELS)
    def test_all_can_be_constructed(self, model_cls: type) -> None:
        instance = model_cls()
        assert isinstance(instance, MetadataComponent)


# ─── Serialization Tests ────────────────────────────────────────

class TestSerialization:
    ALL_INSTANCES: tuple[MetadataComponent, ...] = (
        MetadataApexClass(api_name="Test"),
        MetadataApprovalProcess(api_name="Test"),
        MetadataConnectedApp(api_name="Test"),
        MetadataCustomMetadata(api_name="Test"),
        MetadataCustomSetting(api_name="Test"),
        MetadataDashboard(api_name="Test"),
        MetadataEmailTemplate(api_name="Test"),
        MetadataField(api_name="Test"),
        MetadataFlow(api_name="Test"),
        MetadataFlowVersion(api_name="Test"),
        MetadataFormula(api_name="Test"),
        MetadataGlobalValueSet(api_name="Test"),
        MetadataLayout(api_name="Test"),
        MetadataLightningPage(api_name="Test"),
        MetadataNamedCredential(api_name="Test"),
        MetadataObject(api_name="Test"),
        MetadataPermissionSet(api_name="Test"),
        MetadataProfile(api_name="Test"),
        MetadataPublicGroup(api_name="Test"),
        MetadataQueue(api_name="Test"),
        MetadataQuickAction(api_name="Test"),
        MetadataRecordType(api_name="Test"),
        MetadataRelationship(api_name="Test"),
        MetadataReport(api_name="Test"),
        MetadataRole(api_name="Test"),
        MetadataSharingRule(api_name="Test"),
        MetadataTrigger(api_name="Test"),
        MetadataValidationRule(api_name="Test"),
        MetadataWorkflow(api_name="Test"),
    )

    @pytest.mark.parametrize("instance", ALL_INSTANCES)
    def test_dict_roundtrip(self, instance: MetadataComponent) -> None:
        data = instance.model_dump()
        restored = instance.__class__.model_validate(data)
        assert restored.model_dump() == data

    @pytest.mark.parametrize("instance", ALL_INSTANCES)
    def test_json_roundtrip(self, instance: MetadataComponent) -> None:
        json_str = instance.model_dump_json()
        restored = instance.__class__.model_validate_json(json_str)
        assert restored.model_dump() == instance.model_dump()

    def test_custom_metadata_properties_serialize(self) -> None:
        comp = MetadataComponent(
            api_name="WithProps",
            metadata_properties={"nested": {"a": 1, "b": [1, 2, 3]}},
        )
        data = comp.model_dump()
        assert data["metadata_properties"]["nested"]["b"] == [1, 2, 3]


# ─── Validation Tests ───────────────────────────────────────────

class TestValidation:
    def test_negative_version_raises(self) -> None:
        with pytest.raises(ValidationError):
            MetadataComponent(api_name="Bad", version=-1)

    def test_empty_api_name_allowed_on_base(self) -> None:
        comp = MetadataComponent()
        assert comp.api_name == ""

    def test_relationships_validate_nested(self) -> None:
        with pytest.raises(ValidationError):
            CanonicalRelationship(
                target_type="object",
                target_api_name="Account",
                type="invalid_type",
            )


# ─── Backward Compatibility Tests ───────────────────────────────

class TestBackwardCompatibility:
    def test_extra_fields_ignored_by_default(self) -> None:
        data = {
            "api_name": "Test",
            "type": "test",
            "unknown_field": "should_be_ignored",
        }
        comp = MetadataComponent.model_validate(data)
        assert comp.api_name == "Test"
        assert not hasattr(comp, "unknown_field")

    def test_fields_still_work_with_extra_keys(self) -> None:
        data = {
            "api_name": "MyField",
            "type": "field",
            "object_api_name": "Account",
            "field_type": "text",
            "extra_data": "ignored",
        }
        field = MetadataField.model_validate(data)
        assert field.api_name == "MyField"
        assert field.object_api_name == "Account"
