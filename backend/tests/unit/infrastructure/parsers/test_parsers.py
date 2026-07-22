"""Tests for all 29 concrete metadata parsers."""

from typing import Any

from sfir_backend.domain.canonical import (
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
from sfir_backend.infrastructure.parsers import (
    ApexClassParser,
    ApprovalProcessParser,
    ConnectedAppParser,
    CustomMetadataParser,
    CustomSettingParser,
    DashboardParser,
    EmailTemplateParser,
    FieldParser,
    FlowParser,
    FlowVersionParser,
    FormulaParser,
    GlobalValueSetParser,
    LayoutParser,
    LightningPageParser,
    NamedCredentialParser,
    ObjectParser,
    PermissionSetParser,
    ProfileParser,
    PublicGroupParser,
    QueueParser,
    QuickActionParser,
    RecordTypeParser,
    RelationshipParser,
    ReportParser,
    RoleParser,
    SharingRuleParser,
    TriggerParser,
    ValidationRuleParser,
    WorkflowParser,
)
from sfir_backend.infrastructure.parsers.base import ParserContext


def _parse(parser, data: dict[str, Any], ctx=None) -> Any:
    import asyncio
    return asyncio.run(parser.parse(data, ctx))


def _check(parser, data: dict[str, Any], expected_type: str) -> Any:
    result = _parse(parser, data)
    assert result.errors == [], f"Unexpected errors: {result.errors}"
    assert result.component is not None
    assert result.component.type == expected_type
    assert result.component.api_name == data.get(
        "fullName", data.get("Name", ""),
    )
    return result.component


class TestObjectParser:
    PARSER = ObjectParser()

    def test_parse_basic(self) -> None:
        obj = _check(self.PARSER, {"fullName": "Account"}, "object")
        assert isinstance(obj, MetadataObject)
        assert obj.label == ""

    def test_parse_with_fields(self) -> None:
        obj = _check(self.PARSER, {
            "fullName": "Custom__c",
            "label": "Custom",
            "pluralLabel": "Customs",
            "fields": [
                {"fullName": "Custom__c.Field1__c", "type": "Text", "label": "Field 1"},
                {"fullName": "Custom__c.Field2__c", "type": "Number", "label": "Field 2"},
            ],
        }, "object")
        assert len(obj.fields) == 2
        assert obj.fields[0].api_name == "Custom__c.Field1__c"
        assert obj.fields[0].field_type.value == "text"

    def test_extract_references(self) -> None:
        _obj = _check(self.PARSER, {
            "fullName": "Account",
            "fields": [
                {"fullName": "Account.OwnerId", "type": "Lookup",
                 "referenceTo": "User", "relationshipName": "Owner"},
            ],
        }, "object")
        result = _parse(self.PARSER, {
            "fullName": "Account",
            "fields": [
                {"fullName": "Account.OwnerId", "type": "Lookup",
                 "referenceTo": "User", "relationshipName": "Owner"},
            ],
        })
        assert len(result.references) >= 1
        assert result.references[0].target_api_name == "User"


class TestFieldParser:
    PARSER = FieldParser()

    def test_parse_text(self) -> None:
        field = _check(self.PARSER, {
            "fullName": "Account.Name", "type": "Text", "label": "Name",
            "required": True, "unique": False,
        }, "field")
        assert isinstance(field, MetadataField)
        assert field.field_type.value == "text"
        assert field.required is True

    def test_parse_lookup(self) -> None:
        field = _check(self.PARSER, {
            "fullName": "Account.OwnerId", "type": "Lookup",
            "referenceTo": "User", "relationshipName": "Owner",
            "cascadeDelete": False,
        }, "field")
        assert field.reference_to == "User"
        assert field.relationship_name == "Owner"

    def test_extract_references(self) -> None:
        result = _parse(self.PARSER, {
            "fullName": "Account.OwnerId", "type": "Lookup",
            "referenceTo": "User",
        })
        assert len(result.references) == 1
        assert result.references[0].target_api_name == "User"

    def test_normalizes_field_type(self) -> None:
        field = _check(self.PARSER, {
            "fullName": "Test", "type": "AutoNumber",
        }, "field")
        assert field.field_type.value == "auto_number"


class TestRelationshipParser:
    PARSER = RelationshipParser()

    def test_parse(self) -> None:
        rel = _check(self.PARSER, {
            "fullName": "Account_Owner",
            "source_api_name": "Account",
            "target_api_name": "User",
            "relationship_type": "master_detail",
            "cascade_delete": True,
        }, "relationship")
        assert isinstance(rel, MetadataRelationship)
        assert rel.source_api_name == "Account"
        assert rel.cascade_delete is True


class TestGlobalValueSetParser:
    PARSER = GlobalValueSetParser()

    def test_parse(self) -> None:
        gvs = _check(self.PARSER, {
            "fullName": "Industry",
            "masterLabel": "Industry",
            "customValue": [{"label": "Tech", "value": "Tech"}],
            "grouped": True,
        }, "global_value_set")
        assert isinstance(gvs, MetadataGlobalValueSet)
        assert gvs.master_label == "Industry"
        assert gvs.grouped is True


class TestApexClassParser:
    PARSER = ApexClassParser()

    def test_parse_basic(self) -> None:
        cls = _check(self.PARSER, {
            "fullName": "MyController",
            "apiVersion": 62,
            "body": "public class MyController {}",
        }, "apex_class")
        assert isinstance(cls, MetadataApexClass)
        assert cls.api_version == 62
        assert cls.body == "public class MyController {}"

    def test_parse_tooling_api_format(self) -> None:
        cls = _check(self.PARSER, {
            "Name": "MyController",
            "ApiVersion": 62,
            "Body": "public class MyController {}",
        }, "apex_class")
        assert cls.api_version == 62
        assert cls.body == "public class MyController {}"

    def test_extract_soql_references(self) -> None:
        result = _parse(self.PARSER, {
            "fullName": "MyClass",
            "body": """
                List<Account> accs = [SELECT Id FROM Account];
                List<Contact> cons = [SELECT Id FROM Contact];
            """,
        })
        assert len(result.references) >= 2


class TestTriggerParser:
    PARSER = TriggerParser()

    def test_parse_basic(self) -> None:
        trig = _check(self.PARSER, {
            "fullName": "AccountTrigger",
            "object_api_name": "Account",
            "trigger_events": ["before insert", "after insert"],
        }, "trigger")
        assert isinstance(trig, MetadataTrigger)
        assert trig.object_api_name == "Account"
        assert "before insert" in trig.trigger_events

    def test_extract_references(self) -> None:
        result = _parse(self.PARSER, {
            "fullName": "AccountTrigger",
            "object_api_name": "Account",
        })
        assert len(result.references) == 1
        assert result.references[0].target_api_name == "Account"


class TestFlowParser:
    PARSER = FlowParser()

    def test_parse_basic(self) -> None:
        flow = _check(self.PARSER, {
            "fullName": "MyFlow",
            "processType": "Workflow",
            "status": "active",
            "recordCreates": ["Account"],
            "subflows": ["SubFlow1"],
        }, "flow")
        assert isinstance(flow, MetadataFlow)
        assert flow.process_type == "Workflow"
        assert flow.record_creates == ["Account"]
        assert flow.subflows == ["SubFlow1"]

    def test_parse_with_versions(self) -> None:
        flow = _check(self.PARSER, {
            "fullName": "MyFlow",
            "versions": [
                {"fullName": "v1", "versionNumber": 1},
                {"fullName": "v2", "versionNumber": 2},
            ],
        }, "flow")
        assert len(flow.versions) == 2

    def test_extract_references(self) -> None:
        result = _parse(self.PARSER, {
            "fullName": "MyFlow",
            "recordCreates": ["Account", "Contact"],
            "recordUpdates": ["Opportunity"],
            "subflows": ["SubFlow1"],
        })
        assert len(result.references) == 4


class TestFlowVersionParser:
    PARSER = FlowVersionParser()

    def test_parse(self) -> None:
        fv = _check(self.PARSER, {
            "fullName": "MyFlow_v3",
            "flow_api_name": "MyFlow",
            "versionNumber": 3,
        }, "flow_version")
        assert isinstance(fv, MetadataFlowVersion)
        assert fv.flow_api_name == "MyFlow"
        assert fv.version_number == 3


class TestValidationRuleParser:
    PARSER = ValidationRuleParser()

    def test_parse_basic(self) -> None:
        vr = _check(self.PARSER, {
            "fullName": "Account.MyRule",
            "active": True,
            "errorMessage": "Error!",
            "formula": "Age < 18",
        }, "validation_rule")
        assert isinstance(vr, MetadataValidationRule)
        assert vr.api_name == "Account.MyRule"
        assert vr.object_api_name == "Account"
        assert vr.formula == "Age < 18"

    def test_parse_with_object_api_name(self) -> None:
        vr = _check(self.PARSER, {
            "fullName": "MyRule",
            "object_api_name": "Account",
            "formula": "True",
        }, "validation_rule")
        assert vr.object_api_name == "Account"


class TestFormulaParser:
    PARSER = FormulaParser()

    def test_parse(self) -> None:
        f = _check(self.PARSER, {
            "fullName": "FullNameFormula",
            "object_api_name": "Contact",
            "formula": "FirstName & ' ' & LastName",
            "returnType": "Text",
        }, "formula")
        assert isinstance(f, MetadataFormula)
        assert f.formula_expression == "FirstName & ' ' & LastName"
        assert f.return_type == "Text"


class TestLayoutParser:
    PARSER = LayoutParser()

    def test_parse(self) -> None:
        layout = _check(self.PARSER, {
            "fullName": "Account-Account Layout",
            "layoutType": "Detail",
            "sections": [{"label": "System"}],
        }, "layout")
        assert isinstance(layout, MetadataLayout)
        assert layout.object_api_name == "Account"
        assert len(layout.sections) == 1


class TestRecordTypeParser:
    PARSER = RecordTypeParser()

    def test_parse(self) -> None:
        rt = _check(self.PARSER, {
            "fullName": "Account.Prospect",
            "active": True,
            "businessProcess": "Prospecting",
        }, "record_type")
        assert isinstance(rt, MetadataRecordType)
        assert rt.object_api_name == "Account"
        assert rt.business_process == "Prospecting"


class TestPermissionSetParser:
    PARSER = PermissionSetParser()

    def test_parse(self) -> None:
        ps = _check(self.PARSER, {
            "fullName": "SalesUser",
            "label": "Sales User",
            "userLicense": "Salesforce",
            "hasActivation": True,
        }, "permission_set")
        assert isinstance(ps, MetadataPermissionSet)
        assert ps.user_license == "Salesforce"
        assert ps.has_activation is True


class TestProfileParser:
    PARSER = ProfileParser()

    def test_parse(self) -> None:
        p = _check(self.PARSER, {
            "fullName": "Admin",
            "userLicense": "Salesforce",
            "custom": True,
        }, "profile")
        assert isinstance(p, MetadataProfile)
        assert p.custom is True


class TestReportParser:
    PARSER = ReportParser()

    def test_parse(self) -> None:
        r = _check(self.PARSER, {
            "fullName": "AccountReport",
            "reportType": "Summary",
            "folderName": "Shared",
        }, "report")
        assert isinstance(r, MetadataReport)
        assert r.report_type == "Summary"
        assert r.folder_name == "Shared"


class TestDashboardParser:
    PARSER = DashboardParser()

    def test_parse(self) -> None:
        d = _check(self.PARSER, {
            "fullName": "ExecDashboard",
            "dashboardType": "Specified",
            "components": [{"type": "chart"}],
        }, "dashboard")
        assert isinstance(d, MetadataDashboard)
        assert len(d.components) == 1


class TestWorkflowParser:
    PARSER = WorkflowParser()

    def test_parse(self) -> None:
        w = _check(self.PARSER, {
            "fullName": "AccountWF",
            "object_api_name": "Account",
            "formula_criteria": "Active__c = true",
            "evaluation_criteria": "Everytime",
        }, "workflow")
        assert isinstance(w, MetadataWorkflow)
        assert w.formula_criteria == "Active__c = true"


class TestApprovalProcessParser:
    PARSER = ApprovalProcessParser()

    def test_parse(self) -> None:
        ap = _check(self.PARSER, {
            "fullName": "ExpenseApproval",
            "object_api_name": "Expense__c",
            "record_editability": "ReadOnly",
            "steps": [{"name": "Manager Approval", "order": 1}],
        }, "approval_process")
        assert isinstance(ap, MetadataApprovalProcess)
        assert ap.record_editability == "ReadOnly"


class TestCustomMetadataParser:
    PARSER = CustomMetadataParser()

    def test_parse(self) -> None:
        cm = _check(self.PARSER, {
            "fullName": "CountryCodes",
            "visibility": "Public",
            "fields": [{"name": "Code", "type": "Text"}],
        }, "custom_metadata")
        assert isinstance(cm, MetadataCustomMetadata)
        assert len(cm.fields) == 1


class TestCustomSettingParser:
    PARSER = CustomSettingParser()

    def test_parse(self) -> None:
        cs = _check(self.PARSER, {
            "fullName": "AppConfig",
            "settingType": "hierarchy",
            "visibility": "Protected",
        }, "custom_setting")
        assert isinstance(cs, MetadataCustomSetting)
        assert cs.setting_type == "hierarchy"


class TestLightningPageParser:
    PARSER = LightningPageParser()

    def test_parse(self) -> None:
        lp = _check(self.PARSER, {
            "fullName": "MyCustomPage",
            "masterLabel": "My Custom Page",
            "type": "HomePage",
            "regions": [{"name": "main"}],
        }, "lightning_page")
        assert isinstance(lp, MetadataLightningPage)
        assert lp.master_label == "My Custom Page"
        assert lp.page_type == "HomePage"


class TestQuickActionParser:
    PARSER = QuickActionParser()

    def test_parse(self) -> None:
        qa = _check(self.PARSER, {
            "fullName": "Account.NewTask",
            "type": "Create",
            "targetObject": "Task",
            "object_api_name": "Account",
        }, "quick_action")
        assert isinstance(qa, MetadataQuickAction)
        assert qa.target_object == "Task"


class TestEmailTemplateParser:
    PARSER = EmailTemplateParser()

    def test_parse(self) -> None:
        et = _check(self.PARSER, {
            "fullName": "WelcomeEmail",
            "templateType": "html",
            "subject": "Welcome!",
            "content": "<h1>Welcome</h1>",
        }, "email_template")
        assert isinstance(et, MetadataEmailTemplate)
        assert et.subject == "Welcome!"
        assert et.template_type == "html"


class TestNamedCredentialParser:
    PARSER = NamedCredentialParser()

    def test_parse(self) -> None:
        nc = _check(self.PARSER, {
            "fullName": "ExternalAPI",
            "endpoint": "https://api.example.com",
            "principalType": "NamedUser",
            "protocol": "BasicAuthentication",
        }, "named_credential")
        assert isinstance(nc, MetadataNamedCredential)
        assert nc.endpoint == "https://api.example.com"


class TestConnectedAppParser:
    PARSER = ConnectedAppParser()

    def test_parse(self) -> None:
        ca = _check(self.PARSER, {
            "fullName": "MyApp",
            "version": "2.0",
            "contactEmail": "admin@example.com",
            "oauthConfig": {"scopes": ["api"]},
        }, "connected_app")
        assert isinstance(ca, MetadataConnectedApp)
        assert ca.contact_email == "admin@example.com"


class TestRoleParser:
    PARSER = RoleParser()

    def test_parse(self) -> None:
        r = _check(self.PARSER, {
            "fullName": "CEO",
            "parentRole": "CFO",
            "caseAccessLevel": "Read",
            "mayForecastManager": True,
        }, "role")
        assert isinstance(r, MetadataRole)
        assert r.parent_role == "CFO"
        assert r.may_forecast_manager is True


class TestQueueParser:
    PARSER = QueueParser()

    def test_parse(self) -> None:
        q = _check(self.PARSER, {
            "fullName": "SupportQueue",
            "email": "support@example.com",
            "queueSobjects": [{"objectName": "Case"}],
        }, "queue")
        assert isinstance(q, MetadataQueue)
        assert q.email == "support@example.com"


class TestPublicGroupParser:
    PARSER = PublicGroupParser()

    def test_parse(self) -> None:
        pg = _check(self.PARSER, {
            "fullName": "AllEmployees",
            "members": [{"type": "user", "name": "user@example.com"}],
        }, "public_group")
        assert isinstance(pg, MetadataPublicGroup)
        assert len(pg.members) == 1


class TestSharingRuleParser:
    PARSER = SharingRuleParser()

    def test_parse(self) -> None:
        sr = _check(self.PARSER, {
            "fullName": "AccountSharing",
            "sharedTo": "AllInternalUsers",
            "sharedFrom": "SalesTeam",
            "accessLevel": "Edit",
            "object_api_name": "Account",
        }, "sharing_rule")
        assert isinstance(sr, MetadataSharingRule)
        assert sr.shared_to == "AllInternalUsers"
        assert sr.access_level == "Edit"


class TestParserContextIntegration:
    def test_context_passed_through(self) -> None:
        from sfir_backend.infrastructure.parsers.core import FieldParser

        parser = FieldParser()
        ctx = ParserContext(organization_id="org-1", api_version="62.0")
        result = _parse(parser, {"fullName": "Test", "type": "Text"}, ctx)
        assert result.errors == []
        assert result.component is not None
