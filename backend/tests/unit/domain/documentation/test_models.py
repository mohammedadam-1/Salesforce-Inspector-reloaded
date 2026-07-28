"""Tests for documentation domain models."""

from datetime import UTC, datetime

from sfir_backend.domain.documentation.models import (
    CacheEntry,
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    ExportRequest,
    GenerateRequest,
    GenerationMetricsSnapshot,
    ReportType,
    Section,
    SectionType,
)


class TestEnums:
    def test_documentation_format_values(self) -> None:
        assert DocumentationFormat.MARKDOWN == "markdown"
        assert DocumentationFormat.HTML == "html"
        assert DocumentationFormat.JSON == "json"

    def test_report_type_values(self) -> None:
        assert ReportType.COMPONENT == "component"
        assert ReportType.DEPENDENCY == "dependency"
        assert ReportType.ARCHITECTURE == "architecture"

    def test_section_type_values(self) -> None:
        assert SectionType.OVERVIEW == "overview"
        assert SectionType.PROPERTIES == "properties"
        assert SectionType.DEPENDENCIES == "dependencies"


class TestSection:
    def test_defaults(self) -> None:
        s = Section()
        assert s.title == ""
        assert s.content == ""
        assert s.order == 0
        assert s.section_type == SectionType.CUSTOM

    def test_full(self) -> None:
        s = Section(
            title="Overview",
            content="Some content",
            order=1,
            section_type=SectionType.OVERVIEW,
            metadata={"key": "val"},
        )
        assert s.title == "Overview"
        assert s.content == "Some content"


class TestDocumentationPage:
    def test_defaults(self) -> None:
        p = DocumentationPage()
        assert p.id == ""
        assert p.sections == []
        assert p.format == DocumentationFormat.MARKDOWN

    def test_with_data(self) -> None:
        p = DocumentationPage(
            id="page-1",
            title="Account",
            component_key="object:Account",
            component_type="object",
            api_name="Account",
            sections=[Section(title="Overview", content="test", order=0)],
            word_count=1,
        )
        assert p.id == "page-1"
        assert len(p.sections) == 1
        assert p.word_count == 1


class TestDocumentationReport:
    def test_defaults(self) -> None:
        r = DocumentationReport()
        assert r.id == ""
        assert r.pages == []
        assert r.report_type == ReportType.COMPONENT

    def test_with_data(self) -> None:
        r = DocumentationReport(
            id="report-1",
            title="Test Report",
            report_type=ReportType.DEPENDENCY,
            pages=[DocumentationPage(id="p1")],
            statistics={"total": 1},
        )
        assert r.id == "report-1"
        assert len(r.pages) == 1


class TestGenerateRequest:
    def test_defaults(self) -> None:
        r = GenerateRequest()
        assert r.component_keys == []
        assert r.report_type == ReportType.COMPONENT
        assert r.format == DocumentationFormat.MARKDOWN


class TestExportRequest:
    def test_defaults(self) -> None:
        r = ExportRequest()
        assert r.report_ids == []
        assert r.format == DocumentationFormat.JSON


class TestCacheEntry:
    def test_defaults(self) -> None:
        e = CacheEntry()
        assert e.key == ""
        assert e.ttl_seconds == 300
        assert e.size_bytes == 0


class TestGenerationMetricsSnapshot:
    def test_defaults(self) -> None:
        m = GenerationMetricsSnapshot()
        assert m.total_pages_generated == 0
        assert m.cache_hits == 0
