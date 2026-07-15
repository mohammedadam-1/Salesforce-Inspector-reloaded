"""Tests for parser engine infrastructure: base, registry, engine, validation, normalization, extraction, diagnostics."""  # noqa: E501

import pytest

from sfir_backend.domain.canonical import MetadataComponent, MetadataObject
from sfir_backend.infrastructure.parsers import (
    BaseParser,
    ParserContext,
    ParserEngine,
    ParserMetrics,
    ParserRegistry,
    ReferenceExtractor,
    RelationshipExtractor,
    ValidationEngine,
)
from sfir_backend.infrastructure.parsers.base import ExtractedReference, ParseResult
from sfir_backend.infrastructure.parsers.errors import (
    MalformedMetadataError,
    MissingRequiredFieldError,
    UnsupportedMetadataTypeError,
)
from sfir_backend.infrastructure.parsers.extraction import ExtractedRelationship
from sfir_backend.infrastructure.parsers.normalization import NormalizationEngine

# ─── Base Parser ───────────────────────────────────────────────

class TestBaseParser:
    def test_parse_returns_result_with_defaults(self) -> None:
        class MinimalParser(BaseParser):
            metadata_type = "test"

            def _parse(self, data, context=None):
                return MetadataComponent(api_name="test", type="test")

        parser = MinimalParser()
        result = await_parse(parser, {"key": "val"})

        assert result.metadata_type == "test"
        assert result.component is not None
        assert result.component.api_name == "test"
        assert result.references == []
        assert result.relationships == []
        assert result.warnings == []
        assert result.errors == []
        assert result.duration_ms >= 0

    def test_parse_handles_fatal_error(self) -> None:
        from sfir_backend.infrastructure.parsers.errors import FatalParserError

        class BrokenParser(BaseParser):
            metadata_type = "broken"

            def _parse(self, data, context=None):
                raise FatalParserError("catastrophic failure")

        parser = BrokenParser()
        result = await_parse(parser, {})

        assert result.component is None
        assert len(result.errors) == 1
        assert "catastrophic failure" in result.errors[0]

    def test_parse_handles_non_fatal_error(self) -> None:
        from sfir_backend.infrastructure.parsers.errors import ParserError

        class WarningParser(BaseParser):
            metadata_type = "warn"

            def _parse(self, data, context=None):
                raise ParserError("non-fatal issue")

        parser = WarningParser()
        result = await_parse(parser, {})

        assert result.component is None
        assert len(result.warnings) == 1
        assert "non-fatal" in result.warnings[0]

    def test_extract_references_and_relationships_are_called(self) -> None:
        class RefParser(BaseParser):
            metadata_type = "ref_test"

            def _parse(self, data, context=None):
                return MetadataObject(api_name="Obj1", type="object")

            def _extract_references(self, component, data, context=None):
                return [
                    ExtractedReference(
                        source_api_name="Obj1",
                        source_type="object",
                        target_api_name="Obj2",
                        target_type="object",
                    ),
                ]

            def _extract_relationships(self, component, references, context=None):
                return [
                    ExtractedRelationship(
                        type="references",
                        source_api_name="Obj1",
                        source_type="object",
                        target_api_name="Obj2",
                        target_type="object",
                    ),
                ]

        parser = RefParser()
        result = await_parse(parser, {})

        assert len(result.references) == 1
        assert result.references[0].target_api_name == "Obj2"
        assert len(result.relationships) == 1


# ─── ParserContext ─────────────────────────────────────────────

class TestParserContext:
    def test_defaults(self) -> None:
        ctx = ParserContext()
        assert ctx.organization_id == ""
        assert ctx.api_version is None
        assert ctx.source == "metadata_api"
        assert ctx.options == {}

    def test_custom(self) -> None:
        ctx = ParserContext(
            organization_id="org-1",
            api_version="62.0",
            source="tooling_api",
            options={"parse_body": True},
        )
        assert ctx.organization_id == "org-1"
        assert ctx.api_version == "62.0"


# ─── ParserRegistry ────────────────────────────────────────────

class TestParserRegistry:
    def test_register_and_get(self) -> None:
        from sfir_backend.infrastructure.parsers.core import FieldParser

        registry = ParserRegistry()
        parser = FieldParser()
        registry.register(parser)

        assert registry.has("field")
        retrieved = registry.get("field")
        assert isinstance(retrieved, FieldParser)

    def test_get_unsupported_raises(self) -> None:
        registry = ParserRegistry()
        with pytest.raises(UnsupportedMetadataTypeError):
            registry.get("nonexistent")

    def test_list_types(self) -> None:
        from sfir_backend.infrastructure.parsers.core import FieldParser, ObjectParser

        registry = ParserRegistry()
        registry.register(FieldParser())
        registry.register(ObjectParser())
        types = registry.list_types()
        assert "field" in types
        assert "object" in types

    def test_register_all(self) -> None:
        from sfir_backend.infrastructure.parsers.core import FieldParser, ObjectParser

        registry = ParserRegistry()
        registry.register_all([FieldParser(), ObjectParser()])
        assert len(registry) == 2

    def test_register_empty_type_raises(self) -> None:
        class EmptyParser(BaseParser):
            metadata_type = ""

            def _parse(self, data, context=None):
                return None

        registry = ParserRegistry()
        with pytest.raises(ValueError, match="empty metadata_type"):
            registry.register(EmptyParser())


# ─── ValidationEngine ──────────────────────────────────────────

class TestValidationEngine:
    def test_valid_data_passes(self) -> None:
        engine = ValidationEngine()
        engine.validate({"fullName": "Account"}, "object")

    def test_missing_required_raises(self) -> None:
        engine = ValidationEngine()
        with pytest.raises(MissingRequiredFieldError):
            engine.validate({}, "field")

    def test_non_dict_raises(self) -> None:
        engine = ValidationEngine()
        with pytest.raises(MalformedMetadataError):
            engine.validate("not-a-dict", "object")  # type: ignore[arg-type]

    def test_unsupported_type_raises(self) -> None:
        engine = ValidationEngine()
        with pytest.raises(UnsupportedMetadataTypeError):
            engine.validate_supported_type("unknown_type")


# ─── NormalizationEngine ───────────────────────────────────────

class TestNormalizationEngine:
    def test_basic_mapping(self) -> None:
        engine = NormalizationEngine()
        result = engine.normalize(
            {"fullName": "Account", "label": "Account Label"},
            "object",
        )
        assert result["api_name"] == "Account"
        assert result["label"] == "Account Label"

    def test_type_specific_mapping(self) -> None:
        engine = NormalizationEngine()
        result = engine.normalize(
            {"fullName": "Test__c", "type": "Text", "length": 100, "required": True},
            "field",
        )
        assert result["api_name"] == "Test__c"
        assert result["field_type"] == "Text"
        assert result["length"] == 100
        assert result["required"] is True

    def test_source_platform_added(self) -> None:
        engine = NormalizationEngine()
        result = engine.normalize({"fullName": "Test"}, "object")
        assert result["source_platform"] == "salesforce"

    def test_unknown_field_passed_through(self) -> None:
        engine = NormalizationEngine()
        result = engine.normalize(
            {"fullName": "Test", "unknownField": "value"},
            "object",
        )
        assert result["unknownField"] == "value"


# ─── ReferenceExtractor ────────────────────────────────────────

class TestReferenceExtractor:
    def test_string_ref(self) -> None:
        extractor = ReferenceExtractor()
        comp = MetadataObject(api_name="Account", type="object")
        refs = extractor.extract(comp, {"object_api_name": "Target"})
        assert len(refs) == 0  # "object_api_name" is not in EXTRACTORS for object

    def test_list_ref_with_strings(self) -> None:
        extractor = ReferenceExtractor()
        comp = MetadataComponent(api_name="MyFlow", type="flow")
        refs = extractor.extract(comp, {"record_creates": ["Account", "Contact"]})
        assert len(refs) == 2
        assert refs[0].target_api_name == "Account"
        assert refs[1].target_api_name == "Contact"

    def test_list_ref_with_dicts(self) -> None:
        extractor = ReferenceExtractor()
        comp = MetadataComponent(api_name="MySet", type="permission_set")
        refs = extractor.extract(
            comp,
            {"object_permissions": [{"object_name": "Account"}, {"object_name": "Contact"}]},
        )
        assert len(refs) == 2
        assert refs[0].target_api_name == "Account"


# ─── RelationshipExtractor ─────────────────────────────────────

class TestRelationshipExtractor:
    def test_reference_becomes_relationship(self) -> None:
        extractor = RelationshipExtractor()
        refs = [
            ExtractedReference(
                source_api_name="MyFlow",
                source_type="flow",
                target_api_name="Account",
                target_type="object",
                reference_type="flow_create",
            ),
        ]
        rels = extractor.extract(MetadataComponent(), refs)
        assert len(rels) == 1
        assert rels[0].type == "references"
        assert rels[0].target_api_name == "Account"

    def test_formula_ref_becomes_depends_on(self) -> None:
        extractor = RelationshipExtractor()
        refs = [
            ExtractedReference(
                source_api_name="Rule1",
                source_type="validation_rule",
                target_api_name="Account",
                target_type="object",
                reference_type="formula",
            ),
        ]
        rels = extractor.extract(MetadataComponent(), refs)
        assert rels[0].type == "depends_on"


# ─── ParserEngine ──────────────────────────────────────────────

class TestParserEngine:
    @pytest.fixture
    def engine(self) -> ParserEngine:
        from sfir_backend.infrastructure.parsers.core import FieldParser, ObjectParser

        registry = ParserRegistry()
        registry.register(ObjectParser())
        registry.register(FieldParser())
        return ParserEngine(
            registry=registry,
        )

    @pytest.mark.asyncio
    async def test_parse_object(self, engine: ParserEngine) -> None:
        result = await engine.parse(
            {"fullName": "Account", "label": "Account"},
            "object",
        )
        assert result.component is not None
        assert result.component.api_name == "Account"
        assert result.component.type == "object"
        assert result.metadata_type == "object"

    @pytest.mark.asyncio
    async def test_parse_field(self, engine: ParserEngine) -> None:
        result = await engine.parse(
            {"fullName": "Account.Name", "type": "Text", "label": "Name"},
            "field",
        )
        assert result.component is not None
        assert result.component.api_name == "Account.Name"

    @pytest.mark.asyncio
    async def test_parse_unsupported_type(self, engine: ParserEngine) -> None:
        result = await engine.parse({}, "nonexistent")
        assert result.component is None

    @pytest.mark.asyncio
    async def test_parse_many(self, engine: ParserEngine) -> None:
        items = [
            ({"fullName": "Account"}, "object"),
            ({"fullName": "Contact"}, "object"),
        ]
        results = await engine.parse_many(items)
        assert len(results) == 2
        assert results[0].component is not None
        assert results[1].component is not None

    @pytest.mark.asyncio
    async def test_metrics_recorded(self, engine: ParserEngine) -> None:
        await engine.parse({"fullName": "Test"}, "object")
        snapshot = engine.get_metrics_snapshot()
        assert snapshot["total_parses"] == 1

    @pytest.mark.asyncio
    async def test_parse_batch(self, engine: ParserEngine) -> None:
        items = [
            {"fullName": "A"},
            {"fullName": "B"},
        ]
        results = await engine.parse_batch(items, "object")
        assert len(results) == 2


# ─── ParserMetrics ─────────────────────────────────────────────

class TestParserMetrics:
    def test_record_and_snapshot(self) -> None:
        metrics = ParserMetrics()
        metrics.record_parse("object", 10.5, success=True)
        metrics.record_parse("object", 20.0, success=True)
        metrics.record_parse("field", 5.0, success=False)

        assert metrics.total_parses() == 3
        assert metrics.total_failures() == 1

        stats = metrics.get_stats("object")
        assert stats["count"] == 2
        assert stats["avg_duration_ms"] == 15.25

    def test_empty_stats(self) -> None:
        metrics = ParserMetrics()
        stats = metrics.get_stats("nonexistent")
        assert stats["count"] == 0
        assert stats["avg_duration_ms"] == 0.0


# ─── Helpers ────────────────────────────────────────────────────

def await_parse(parser: BaseParser, raw: dict, ctx: ParserContext | None = None) -> ParseResult:  # type: ignore[return]
    """Synchronously await a parser's parse method."""
    import asyncio
    return asyncio.run(parser.parse(raw, ctx))
