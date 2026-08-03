"""Tests for the CanonicalParserAdapter and its pipeline integration."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import pytest

from sfir_backend.domain.canonical import (
    MetadataApprovalProcess,
    MetadataConnectedApp,
    MetadataCustomMetadata,
    MetadataDashboard,
    MetadataEmailTemplate,
    MetadataField,
    MetadataFlow,
    MetadataFlowVersion,
    MetadataFormula,
    MetadataGlobalValueSet,
    MetadataLightningPage,
    MetadataNamedCredential,
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
    MetadataWorkflow,
)
from sfir_backend.infrastructure.parsers.base import ParserContext
from sfir_backend.infrastructure.salesforce.parsers.base import MetadataParser
from sfir_backend.infrastructure.salesforce.parsers.canonical_adapter import (
    CanonicalParserAdapter,
    build_canonical_parser_adapters,
)
from sfir_backend.infrastructure.salesforce.parsers.registry import ParserRegistry
from sfir_backend.infrastructure.salesforce.parsers.apex import ApexClassParser


@pytest.fixture
def context() -> ParserContext:
    return ParserContext(organization_id="org-123", source="test")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


class TestCanonicalParserAdapter:
    def test_implements_metadata_parser_interface(self) -> None:
        adapters = build_canonical_parser_adapters()
        assert len(adapters) > 0
        for adapter in adapters:
            assert isinstance(adapter, MetadataParser)

    def test_can_parse_maps_salesforce_type(self) -> None:
        adapters = build_canonical_parser_adapters()
        # each of these Salesforce types must be claimable by exactly one adapter
        for sf_type in ["Flow", "Profile", "Role", "Queue", "Report", "Dashboard"]:
            matches = [a for a in adapters if a.can_parse(sf_type)]
            assert len(matches) == 1, f"{sf_type} matched {len(matches)} adapters"

    def test_can_parse_rejects_unmapped(self) -> None:
        adapters = build_canonical_parser_adapters()
        for adapter in adapters:
            assert not adapter.can_parse("ApexClass")
            assert not adapter.can_parse("CustomObject")
            assert not adapter.can_parse("Layout")
            assert not adapter.can_parse("ValidationRule")
            assert not adapter.can_parse("UnknownType")

    def test_metadata_type_is_snake_case(self) -> None:
        adapters = build_canonical_parser_adapters()
        for adapter in adapters:
            assert adapter.metadata_type == adapter.metadata_type.lower()

    def test_parse_produces_canonical_component(self, context: ParserContext) -> None:
        adapter = next(
            a for a in build_canonical_parser_adapters(context=context)
            if a.can_parse("Flow")
        )
        result = _run(adapter.parse({
            "fullName": "MyFlow",
            "label": "My Flow",
            "processType": "Flow",
            "status": "active",
        }))
        assert result.success is True
        assert result.data is not None
        assert isinstance(result.data, MetadataFlow)
        assert result.data.api_name == "MyFlow"
        assert result.data.label == "My Flow"
        assert result.data.type == "flow"

    def test_parse_failure_propagates_errors(self, context: ParserContext) -> None:
        adapter = next(
            a for a in build_canonical_parser_adapters(context=context)
            if a.can_parse("Flow")
        )
        # FlowParser with missing data still produces a component (empty api_name);
        # simulate a hard failure via an adapter wrapping a parser that errors.
        class _Exploding:
            metadata_type = "exploding"
            async def parse(self, raw: dict[str, Any], context=None):
                from sfir_backend.infrastructure.parsers.base import ParseResult
                return ParseResult(
                    component=None,
                    errors=["boom"],
                    metadata_type="exploding",
                )

        bad = CanonicalParserAdapter(["Exploding"], _Exploding(), context=context)  # type: ignore[arg-type]
        result = _run(bad.parse({"x": 1}))
        assert result.success is False
        assert result.data is None
        assert "boom" in result.errors

    def test_parse_no_component_no_errors_is_failure(self, context: ParserContext) -> None:
        class _Silent:
            metadata_type = "silent"
            async def parse(self, raw: dict[str, Any], context=None):
                from sfir_backend.infrastructure.parsers.base import ParseResult
                return ParseResult(component=None, metadata_type="silent")

        adapter = CanonicalParserAdapter(["Silent"], _Silent(), context=context)  # type: ignore[arg-type]
        result = _run(adapter.parse({"x": 1}))
        assert result.success is False
        assert result.data is None
        assert len(result.errors) == 1

    def test_parse_body_delegates(self, context: ParserContext) -> None:
        adapter = next(
            a for a in build_canonical_parser_adapters(context=context)
            if a.can_parse("Flow")
        )
        result = _run(adapter.parse_body("{}"))
        # Body without fullName -> parser still produces an empty component
        assert result.success is True
        assert result.data is not None


class TestCanonicalAdapterCoverage:
    """Every broad-parser type must be reachable behind the adapter set."""

    @pytest.mark.parametrize(
        ("sf_type", "expected_cls"),
        [
            ("Role", MetadataRole),
            ("Queue", MetadataQueue),
            ("PublicGroup", MetadataPublicGroup),
            ("SharingRule", MetadataSharingRule),
            ("CustomField", MetadataField),
            ("GlobalValueSet", MetadataGlobalValueSet),
            ("Relationship", MetadataRelationship),
            ("CustomMetadata", MetadataCustomMetadata),
            ("Flow", MetadataFlow),
            ("FlowVersion", MetadataFlowVersion),
            ("EmailTemplate", MetadataEmailTemplate),
            ("NamedCredential", MetadataNamedCredential),
            ("ConnectedApp", MetadataConnectedApp),
            ("RecordType", MetadataRecordType),
            ("PermissionSet", MetadataPermissionSet),
            ("Profile", MetadataProfile),
            ("Report", MetadataReport),
            ("Dashboard", MetadataDashboard),
            ("LightningPage", MetadataLightningPage),
            ("QuickAction", MetadataQuickAction),
            ("Formula", MetadataFormula),
            ("WorkflowRule", MetadataWorkflow),
            ("ApprovalProcess", MetadataApprovalProcess),
        ],
    )
    def test_type_covered(
        self, sf_type: str, expected_cls: type, context: ParserContext,
    ) -> None:
        adapters = build_canonical_parser_adapters(context=context)
        matches = [a for a in adapters if a.can_parse(sf_type)]
        assert len(matches) == 1, f"{sf_type} should be covered by exactly one adapter"
        result = _run(matches[0].parse({"fullName": "Xyz"}))
        assert result.success is True
        assert isinstance(result.data, expected_cls)

    def test_all_adapters_have_unique_registry_keys(self) -> None:
        adapters = build_canonical_parser_adapters()
        keys = [a.metadata_type for a in adapters]
        assert len(keys) == len(set(keys))


class TestParserRegistryIntegration:
    def test_narrow_parser_wins_for_its_types(self) -> None:
        registry = ParserRegistry()
        registry.register(_NarrowDummy())
        for adapter in build_canonical_parser_adapters():
            registry.register(adapter)
        parser = registry.get("ApexClass")
        assert isinstance(parser, _NarrowDummy)

    def test_adapter_handles_new_types(self) -> None:
        registry = ParserRegistry()
        registry.register(_NarrowDummy())
        for adapter in build_canonical_parser_adapters():
            registry.register(adapter)
        parser = registry.get("Flow")
        assert isinstance(parser, CanonicalParserAdapter)
        assert parser.metadata_type == "flow"

    def test_generic_fallback_for_unknown(self) -> None:
        registry = ParserRegistry()
        registry.register(_NarrowDummy())
        for adapter in build_canonical_parser_adapters():
            registry.register(adapter)
        parser = registry.get("TotallyUnknown")
        assert parser.metadata_type == "Generic"

    async def test_registry_parse_returns_canonical_component(self) -> None:
        registry = ParserRegistry()
        registry.register(_NarrowDummy())
        for adapter in build_canonical_parser_adapters():
            registry.register(adapter)
        result = await registry.parse("Flow", {
            "fullName": "MyFlow", "processType": "Flow", "status": "active",
        })
        assert result.success is True
        assert isinstance(result.data, MetadataFlow)
        assert result.data.api_name == "MyFlow"


class _NarrowDummy(MetadataParser):
    metadata_type = "ApexClass"

    def can_parse(self, component_type: str) -> bool:
        return component_type in {"ApexClass", "ApexClassMember"}

    async def parse(self, raw: dict[str, Any]):
        from sfir_backend.infrastructure.salesforce.parsers.base import ParsingResult
        return ParsingResult.ok(raw)

    async def parse_body(self, body: str):
        from sfir_backend.infrastructure.salesforce.parsers.base import ParsingResult
        return await self.parse({"Body": body})


class TestContainerWiring:
    """The DI container must register the canonical adapters behind ParserStage."""

    def test_container_registry_has_narrow_and_adapters(self) -> None:
        from sfir_backend.config.container import Container
        from sfir_backend.config.settings import Settings

        container = Container(Settings(environment="testing"))
        # _make_parser_registry is the exact wiring used at startup without
        # requiring a database session (services register lazily).
        registry = container._make_parser_registry()
        assert isinstance(registry, ParserRegistry)

        # Narrow parser still wins for its 5 types (registered first).
        assert isinstance(registry.get("ApexClass"), ApexClassParser)

        # Canonical adapters handle the remaining types.
        flow_parser = registry.get("Flow")
        assert isinstance(flow_parser, CanonicalParserAdapter)
        assert flow_parser.metadata_type == "flow"

        profile_parser = registry.get("Profile")
        assert isinstance(profile_parser, CanonicalParserAdapter)
        assert profile_parser.metadata_type == "profile"


class TestParserStageIntegration:
    """End-to-end: ParserStage -> CanonicalMappingStage with wired adapters."""

    @staticmethod
    def _make_context(component_type: str, raw: list[dict]):
        from sfir_backend.application.pipeline.pipeline_context import PipelineContext

        org = UUID("11111111-1111-1111-1111-111111111111")
        conn = UUID("22222222-2222-2222-2222-222222222222")
        job = UUID("33333333-3333-3333-3333-333333333333")
        return PipelineContext(
            organization_id=org,
            connection_id=conn,
            sync_job_id=job,
            component_type=component_type,
            raw_components=raw,
        )

    async def test_flow_flows_through_parser_and_mapping(self) -> None:
        from sfir_backend.application.pipeline.stages.canonical_mapping_stage import (
            CanonicalMappingStage,
        )
        from sfir_backend.application.pipeline.stages.parser_stage import ParserStage
        from sfir_backend.config.container import Container
        from sfir_backend.config.settings import Settings

        container = Container(Settings(environment="testing"))
        parser_stage = ParserStage(parser_registry=container._make_parser_registry())
        mapping_stage = CanonicalMappingStage(mapper=container._make_canonical_mapper())

        context = self._make_context("Flow", [
            {"fullName": "MyFlow", "label": "My Flow", "processType": "Flow", "status": "active"},
        ])
        context = await parser_stage.execute(context)
        assert context.parse_errors == []
        assert len(context.parsed_components) == 1
        assert isinstance(context.parsed_components[0], MetadataFlow)

        context = await mapping_stage.execute(context)
        assert context.mapping_errors == []
        assert len(context.canonical_components) == 1
        # MetadataComponentStrategy passes canonical components through unchanged
        assert context.canonical_components[0] is context.parsed_components[0]

    async def test_profile_flows_through_parser_and_mapping(self) -> None:
        from sfir_backend.application.pipeline.stages.canonical_mapping_stage import (
            CanonicalMappingStage,
        )
        from sfir_backend.application.pipeline.stages.parser_stage import ParserStage
        from sfir_backend.config.container import Container
        from sfir_backend.config.settings import Settings

        container = Container(Settings(environment="testing"))
        parser_stage = ParserStage(parser_registry=container._make_parser_registry())
        mapping_stage = CanonicalMappingStage(mapper=container._make_canonical_mapper())

        context = self._make_context("Profile", [{"fullName": "Admin", "label": "Administrator"}])
        context = await parser_stage.execute(context)
        assert context.parse_errors == []
        assert len(context.parsed_components) == 1
        assert isinstance(context.parsed_components[0], MetadataProfile)

        context = await mapping_stage.execute(context)
        assert context.mapping_errors == []
        assert len(context.canonical_components) == 1
        assert isinstance(context.canonical_components[0], MetadataProfile)

    async def test_unknown_type_falls_back_to_generic(self) -> None:
        from sfir_backend.application.pipeline.stages.parser_stage import ParserStage
        from sfir_backend.config.container import Container
        from sfir_backend.config.settings import Settings

        container = Container(Settings(environment="testing"))
        parser_stage = ParserStage(parser_registry=container._make_parser_registry())

        context = self._make_context("TotallyUnknown", [{"Name": "Xyz"}])
        context = await parser_stage.execute(context)
        assert context.parse_errors == []
        assert len(context.parsed_components) == 1
        # Generic fallback returns the raw dict
        assert isinstance(context.parsed_components[0], dict)
