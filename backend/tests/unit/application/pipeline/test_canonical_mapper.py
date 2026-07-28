"""Comprehensive tests for the Canonical Mapper."""

from datetime import datetime

import pytest

from sfir_backend.application.pipeline.mapper.canonical_mapper import CanonicalMapper
from sfir_backend.application.pipeline.mapper.strategies import (
    ApexClassStrategy,
    ApexTriggerStrategy,
    DashboardStrategy,
    EmailTemplateStrategy,
    FlowStrategy,
    GenericDictStrategy,
    LayoutStrategy,
    LightningStrategy,
    MetadataComponentStrategy,
    ObjectStrategy,
    PermissionSetStrategy,
    ProfileStrategy,
    QueueStrategy,
    ReportStrategy,
    RoleStrategy,
    SharingRuleStrategy,
    StaticResourceStrategy,
    ValidationRuleStrategy,
    WorkflowRuleStrategy,
)
from sfir_backend.domain.canonical.access import MetadataQueue, MetadataRole, MetadataSharingRule
from sfir_backend.domain.canonical.base import MetadataComponent
from sfir_backend.domain.canonical.code import MetadataApexClass, MetadataTrigger
from sfir_backend.domain.canonical.core import MetadataField, MetadataObject
from sfir_backend.domain.canonical.flows import MetadataFlow
from sfir_backend.domain.canonical.integration import MetadataEmailTemplate
from sfir_backend.domain.canonical.layouts import MetadataLayout
from sfir_backend.domain.canonical.permissions import MetadataPermissionSet, MetadataProfile
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.canonical.ui import MetadataLightningPage
from sfir_backend.domain.canonical.validation import MetadataValidationRule
from sfir_backend.domain.canonical.workflows import MetadataWorkflow
from sfir_backend.domain.metadata.analytics import Dashboard, Report
from sfir_backend.domain.metadata.apex import ApexClass, ApexTrigger
from sfir_backend.domain.metadata.content import EmailTemplate, StaticResource
from sfir_backend.domain.metadata.flows import Flow, FlowElement, FlowStage, FlowVariable
from sfir_backend.domain.metadata.layouts import Layout, LayoutSection, RelatedListItem
from sfir_backend.domain.metadata.lightning import LightingComponentBundle
from sfir_backend.domain.metadata.objects import CustomField, CustomObject, PicklistValue, ValidationRule
from sfir_backend.domain.metadata.profiles import PermissionSet, Profile
from sfir_backend.domain.metadata.security import Queue, Role, SharingCriteriaRule
from sfir_backend.domain.metadata.workflows import WorkflowRule


@pytest.fixture
def mapper() -> CanonicalMapper:
    m = CanonicalMapper()
    m.register(MetadataComponentStrategy())
    m.register(ApexClassStrategy())
    m.register(ApexTriggerStrategy())
    m.register(ObjectStrategy())
    m.register(ValidationRuleStrategy())
    m.register(FlowStrategy())
    m.register(LayoutStrategy())
    m.register(ProfileStrategy())
    m.register(PermissionSetStrategy())
    m.register(EmailTemplateStrategy())
    m.register(ReportStrategy())
    m.register(DashboardStrategy())
    m.register(RoleStrategy())
    m.register(QueueStrategy())
    m.register(SharingRuleStrategy())
    m.register(WorkflowRuleStrategy())
    m.register(LightningStrategy())
    m.register(StaticResourceStrategy())
    m.register(GenericDictStrategy())
    return m


class TestApexClassMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(name="MyClass", body="public class MyClass {}", api_version=58)
        result = mapper.map([apex])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataApexClass)
        assert mapped.api_name == "MyClass"
        assert mapped.body == "public class MyClass {}"
        assert mapped.api_version == 58
        assert mapped.type == "apex_class"

    def test_minimal_fields(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(name="Minimal", body="class Minimal {}")
        result = mapper.map([apex])
        assert len(result) == 1
        assert result[0].api_name == "Minimal"
        assert result[0].api_version is None

    def test_with_symbols(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(
            name="SymbolTest", body="class SymbolTest {}",
            symbols=[{"type": "method", "name": "doStuff"}],
        )
        result = mapper.map([apex])
        props = result[0].metadata_properties
        assert props["symbols"] == [{"type": "method", "name": "doStuff"}]

    def test_immutability(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(name="Original", body="class Original {}")
        result = mapper.map([apex])
        assert len(result) == 1
        assert apex.name == "Original"


class TestApexTriggerMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        trig = ApexTrigger(name="MyTrigger", body="trigger MyTrigger on Account (before insert) {}", object_type="Account")  # noqa: E501
        result = mapper.map([trig])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataTrigger)
        assert mapped.api_name == "MyTrigger"
        assert mapped.object_api_name == "Account"
        assert mapped.type == "trigger"

    def test_trigger_events(self, mapper: CanonicalMapper) -> None:
        trig = ApexTrigger(
            name="EventTest", body="trigger EventTest on Account (before insert, after update) {}",
            object_type="Account",
        )
        result = mapper.map([trig])
        assert result[0].object_api_name == "Account"

    def test_minimal_fields(self, mapper: CanonicalMapper) -> None:
        trig = ApexTrigger(name="Min", body="trigger Min on Object__c (before insert) {}", object_type="Object__c")  # noqa: E501
        result = mapper.map([trig])
        assert result[0].api_name == "Min"


class TestObjectMapping:
    def test_basic_object(self, mapper: CanonicalMapper) -> None:
        obj = CustomObject(name="MyObject__c", label="My Object", plural_label="My Objects")
        result = mapper.map([obj])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataObject)
        assert mapped.api_name == "MyObject__c"
        assert mapped.label == "My Object"
        assert mapped.plural_label == "My Objects"
        assert mapped.type == "object"

    def test_with_fields(self, mapper: CanonicalMapper) -> None:
        field = CustomField(name="TestField__c", label="Test Field", field_type="Text")
        obj = CustomObject(name="Obj__c", fields=[field])
        result = mapper.map([obj])
        mapped = result[0]
        assert len(mapped.fields) == 1
        assert mapped.fields[0].api_name == "Obj__c.TestField__c"
        assert mapped.fields[0].label == "Test Field"

    def test_object_properties(self, mapper: CanonicalMapper) -> None:
        obj = CustomObject(
            name="Full__c", sharing_model="ReadWrite", deployment_status="Deployed",
            enable_feeds=True, enable_history=True, enable_reports=True,
            enable_search=True, enable_sharing=False,
        )
        result = mapper.map([obj])
        m = result[0]
        assert m.sharing_model == "ReadWrite"
        assert m.deployment_status == "Deployed"
        assert m.enable_feeds is True
        assert m.enable_reports is True

    def test_fields_with_picklist(self, mapper: CanonicalMapper) -> None:
        pv = PicklistValue(label="Opt1", value="opt1", default=True)
        field = CustomField(
            name="PickField__c", label="Picklist", field_type="Picklist",
            picklist_values=[pv], required=True,
        )
        obj = CustomObject(name="PickObj__c", fields=[field])
        result = mapper.map([obj])
        mf = result[0].fields[0]
        assert mf.required is True
        assert len(mf.picklist_values) == 1


class TestValidationRuleMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        rule = ValidationRule(name="MyRule", formula="Field1__c > 100", error_message="Too high")
        result = mapper.map([rule])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataValidationRule)
        assert mapped.api_name == "MyRule"
        assert mapped.formula == "Field1__c > 100"
        assert mapped.error_message == "Too high"
        assert mapped.active is True


class TestFlowMapping:
    def test_basic_flow(self, mapper: CanonicalMapper) -> None:
        flow = Flow(name="MyFlow", label="My Flow", process_type="Flow", status="Active")
        result = mapper.map([flow])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataFlow)
        assert mapped.api_name == "MyFlow"
        assert mapped.process_type == "Flow"

    def test_flow_with_elements(self, mapper: CanonicalMapper) -> None:
        flow = Flow(
            name="FullFlow", label="Full",
            variables=[FlowVariable(name="v1", data_type="String")],
            stages=[FlowStage(name="s1", label="Step 1")],
            elements=[FlowElement(name="e1", element_type="Action")],
        )
        result = mapper.map([flow])
        m = result[0]
        assert len(m.variables) == 1
        assert len(m.stages) == 1
        assert len(m.elements) == 1


class TestLayoutMapping:
    def test_basic_layout(self, mapper: CanonicalMapper) -> None:
        layout = Layout(name="MyLayout", object_type="Account")
        result = mapper.map([layout])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataLayout)
        assert mapped.api_name == "MyLayout"
        assert mapped.object_api_name == "Account"

    def test_layout_with_sections(self, mapper: CanonicalMapper) -> None:
        layout = Layout(
            name="FullLayout", object_type="Account",
            sections=[LayoutSection(label="Section1", columns=2)],
            related_lists=[RelatedListItem(object_name="Contact", label="Contacts")],
        )
        result = mapper.map([layout])
        m = result[0]
        assert len(m.sections) == 1
        assert len(m.related_lists) == 1


class TestProfileMapping:
    def test_basic_profile(self, mapper: CanonicalMapper) -> None:
        prof = Profile(name="Admin", user_license="Salesforce")
        result = mapper.map([prof])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataProfile)
        assert mapped.api_name == "Admin"
        assert mapped.user_license == "Salesforce"

    def test_profile_with_permissions(self, mapper: CanonicalMapper) -> None:
        from sfir_backend.domain.metadata.profiles import ObjectPermission
        prof = Profile(
            name="CustomProfile",
            object_permissions=[ObjectPermission(object_name="Account", allow_read=True)],
        )
        result = mapper.map([prof])
        assert len(result[0].object_permissions) == 1


class TestPermissionSetMapping:
    def test_basic_permission_set(self, mapper: CanonicalMapper) -> None:
        ps = PermissionSet(name="MyPS", label="My Permission Set")
        result = mapper.map([ps])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataPermissionSet)
        assert mapped.api_name == "MyPS"
        assert mapped.label == "My Permission Set"


class TestEmailTemplateMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        et = EmailTemplate(name="Welcome Email", developer_name="Welcome_Email", subject="Welcome", body="Hello {{!User.Name}}")  # noqa: E501
        result = mapper.map([et])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataEmailTemplate)
        assert mapped.api_name == "Welcome_Email"
        assert mapped.subject == "Welcome"


class TestReportMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        r = Report(name="MyReport", label="My Report", object_type="Account", report_type="Tabular")
        result = mapper.map([r])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataReport)
        assert mapped.api_name == "MyReport"
        assert mapped.object_api_name == "Account"


class TestDashboardMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        d = Dashboard(name="MyDash", label="My Dashboard", dashboard_type="SpecifiedUser")
        result = mapper.map([d])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataDashboard)
        assert mapped.api_name == "MyDash"


class TestSecurityMapping:
    def test_role(self, mapper: CanonicalMapper) -> None:
        r = Role(name="CEO", parent_role=None)
        result = mapper.map([r])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataRole)
        assert mapped.api_name == "CEO"

    def test_queue(self, mapper: CanonicalMapper) -> None:
        q = Queue(name="Support Queue", label="Support")
        result = mapper.map([q])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataQueue)
        assert mapped.api_name == "Support Queue"

    def test_sharing_rule(self, mapper: CanonicalMapper) -> None:
        sr = SharingCriteriaRule(name="AccountSharing", shared_object="Account", access_level="Read")
        result = mapper.map([sr])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataSharingRule)
        assert mapped.object_api_name == "Account"


class TestWorkflowMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        wf = WorkflowRule(name="MyWorkflow", object_type="Account", formula="Active__c = true")
        result = mapper.map([wf])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataWorkflow)
        assert mapped.api_name == "MyWorkflow"
        assert mapped.formula_criteria == "Active__c = true"


class TestLightningMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        lcb = LightingComponentBundle(name="myComponent", description="A component")
        result = mapper.map([lcb])
        assert len(result) == 1
        mapped = result[0]
        assert isinstance(mapped, MetadataLightningPage)
        assert mapped.api_name == "myComponent"


class TestStaticResourceMapping:
    def test_basic_mapping(self, mapper: CanonicalMapper) -> None:
        sr = StaticResource(name="MyResource", content_type="application/zip")
        result = mapper.map([sr])
        assert len(result) == 1
        assert result[0].api_name == "MyResource"


class TestMetadataComponentPassthrough:
    def test_passthrough(self, mapper: CanonicalMapper) -> None:
        mc = MetadataComponent(api_name="Direct", type="custom_type")
        result = mapper.map([mc])
        assert len(result) == 1
        assert result[0] is mc

    def test_passthrough_subclass(self, mapper: CanonicalMapper) -> None:
        mc = MetadataApexClass(api_name="Sub", body="class Sub {}")
        result = mapper.map([mc])
        assert len(result) == 1
        assert result[0] is mc


class TestGenericDictMapping:
    def test_dict_fallback(self, mapper: CanonicalMapper) -> None:
        result = mapper.map([{"Name": "Test", "type": "CustomMetadata", "Description": "desc"}])
        assert len(result) == 1
        assert result[0].api_name == "Test"
        assert result[0].type == "CustomMetadata"

    def test_dict_no_name(self, mapper: CanonicalMapper) -> None:
        result = mapper.map([{"type": "Something"}])
        assert len(result) == 1
        assert result[0].api_name == ""


class TestEdgeCases:
    def test_empty_list(self, mapper: CanonicalMapper) -> None:
        result = mapper.map([])
        assert result == []

    def test_unknown_type_returns_none(self, mapper: CanonicalMapper) -> None:
        result = mapper.map([42, "string", None])
        assert result == []

    def test_mixed_types(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(name="Mixed", body="class Mixed {}")
        rule = ValidationRule(name="VR1", formula="true", error_message="Err")
        result = mapper.map([apex, rule])
        assert len(result) == 2
        assert isinstance(result[0], MetadataApexClass)
        assert isinstance(result[1], MetadataValidationRule)

    def test_large_batch(self, mapper: CanonicalMapper) -> None:
        items = [ApexClass(name=f"Class{i}", body=f"class Class{i} {{}}") for i in range(1000)]
        result = mapper.map(items)
        assert len(result) == 1000

    def test_deterministic_ordering(self, mapper: CanonicalMapper) -> None:
        items = [ApexClass(name=f"Class{i}", body=f"class Class{i} {{}}") for i in range(100)]
        result1 = mapper.map(items)
        result2 = mapper.map(items)
        for r1, r2 in zip(result1, result2):
            assert r1.api_name == r2.api_name
            assert r1.body == r2.body

    def test_missing_optional_fields(self, mapper: CanonicalMapper) -> None:
        apex = ApexClass(name="Minimal", body="class Minimal {}")
        result = mapper.map([apex])
        assert result[0].api_version is None
        assert result[0].description is None
        assert result[0].namespace is None


class TestCanonicalMappingStage:
    @pytest.mark.asyncio
    async def test_stage_updates_context(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import CanonicalMappingStage

        m = CanonicalMapper()
        m.register(MetadataComponentStrategy())
        m.register(ApexClassStrategy())
        m.register(GenericDictStrategy())
        stage = CanonicalMappingStage(mapper=m)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
            component_type="ApexClass",
        )
        ctx.parsed_components = [ApexClass(name="StageTest", body="class StageTest {}")]

        result = await stage.execute(ctx)
        assert len(result.mapped_components) == 1
        assert len(result.canonical_components) == 1
        assert result.mapped_components[0].api_name == "StageTest"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stage_empty_parsed(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import CanonicalMappingStage

        m = CanonicalMapper()
        m.register(MetadataComponentStrategy())
        stage = CanonicalMappingStage(mapper=m)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.parsed_components = []
        result = await stage.execute(ctx)
        assert len(result.mapped_components) == 0
        assert len(result.canonical_components) == 0
        assert result.success is True

    @pytest.mark.asyncio
    async def test_stage_partial_failure(self) -> None:
        from uuid import UUID
        from sfir_backend.application.pipeline import PipelineContext
        from sfir_backend.application.pipeline.stages import CanonicalMappingStage

        m = CanonicalMapper()
        m.register(ApexClassStrategy())
        stage = CanonicalMappingStage(mapper=m)

        ctx = PipelineContext(
            organization_id=UUID("00000000-0000-0000-0000-000000000001"),
            connection_id=UUID("00000000-0000-0000-0000-000000000002"),
            sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        )
        ctx.parsed_components = [ApexClass(name="Test", body="class Test {}"), None, "invalid"]
        result = await stage.execute(ctx)
        assert len(result.mapped_components) == 1
        assert len(result.canonical_components) == 1
        assert len(result.errors) == 1
