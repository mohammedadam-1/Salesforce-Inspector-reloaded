"""Comprehensive tests for the Documentation Engine."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest

from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    ExportRequest,
    GenerateRequest,
    ReportType,
    Section,
    SectionType,
)
from sfir_backend.domain.graph.models import EdgeType, Graph, GraphEdge, GraphNode, NodeType
from sfir_backend.infrastructure.documentation.cache import DocumentationCache
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine
from sfir_backend.infrastructure.documentation.exporter import (
    ExportCoordinator,
    JSONExporter,
)
from sfir_backend.infrastructure.documentation.generator import (
    DocumentationGenerator,
)
from sfir_backend.infrastructure.documentation.metrics import GenerationMetrics
from sfir_backend.infrastructure.documentation.renderers import (
    HTMLRenderer,
    MarkdownRenderer,
)
from sfir_backend.infrastructure.documentation.reports import (
    ArchitectureReportGenerator,
    DependencyReportGenerator,
    ImpactReportGenerator,
    MetadataReportGenerator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_graph() -> Graph:
    g = Graph()
    nodes = {
        "object:Account": GraphNode(node_type=NodeType.OBJECT, api_name="Account",
                                     label="Account", description="Customer account"),
        "field:Account.Name": GraphNode(node_type=NodeType.FIELD, api_name="Account.Name",
                                         label="Name"),
        "field:Account.Phone": GraphNode(node_type=NodeType.FIELD, api_name="Account.Phone",
                                          label="Phone"),
        "apex_class:AccountService": GraphNode(node_type=NodeType.APEX_CLASS,
                                                api_name="AccountService"),
        "validation_rule:Account.ValidName": GraphNode(
            node_type=NodeType.VALIDATION_RULE, api_name="Account.ValidName",
        ),
        "flow:AccountFlow": GraphNode(node_type=NodeType.FLOW, api_name="AccountFlow"),
        "layout:Account-Account Layout": GraphNode(
            node_type=NodeType.LAYOUT, api_name="Account-Account Layout",
        ),
        "permission_set:AccountAdmin": GraphNode(
            node_type=NodeType.PERMISSION_SET, api_name="AccountAdmin",
        ),
        "report:AccountReport": GraphNode(node_type=NodeType.REPORT, api_name="AccountReport"),
    }
    for key, node in nodes.items():
        g.nodes[key] = node
        g.outgoing[key] = []
        g.incoming[key] = []

    edges = [
        ("object:Account", "field:Account.Name", EdgeType.CONTAINS),
        ("object:Account", "field:Account.Phone", EdgeType.CONTAINS),
        ("apex_class:AccountService", "object:Account", EdgeType.REFERENCES),
        ("validation_rule:Account.ValidName", "field:Account.Name", EdgeType.REFERENCES),
        ("flow:AccountFlow", "object:Account", EdgeType.REFERENCES),
        ("layout:Account-Account Layout", "object:Account", EdgeType.REFERENCES),
        ("permission_set:AccountAdmin", "object:Account", EdgeType.REFERENCES),
        ("report:AccountReport", "object:Account", EdgeType.REFERENCES),
    ]
    for src, tgt, etype in edges:
        eid = f"{src}--[{etype.value}]-->{tgt}"
        g.edges[eid] = GraphEdge(id=eid, source_id=src, target_id=tgt, edge_type=etype)
        g.outgoing[src].append(eid)
        g.incoming[tgt].append(eid)

    return g


@pytest.fixture
def mock_engine() -> MagicMock:
    eng = MagicMock()
    eng.graph = Graph()
    return eng


# ---------------------------------------------------------------------------
# MarkdownRenderer
# ---------------------------------------------------------------------------

class TestMarkdownRenderer:
    def test_render_page(self) -> None:
        renderer = MarkdownRenderer()
        page = DocumentationPage(
            title="Test",
            api_name="TestApi",
            component_type="object",
            sections=[
                Section(title="Sec1", content="Content 1", order=0),
            ],
        )
        md = renderer.render_page(page)
        assert "# Test" in md
        assert "TestApi" in md
        assert "Sec1" in md
        assert "Content 1" in md

    def test_render_page_no_sections(self) -> None:
        renderer = MarkdownRenderer()
        page = DocumentationPage(title="Empty", api_name="E")
        md = renderer.render_page(page)
        assert "# Empty" in md

    def test_render_table(self) -> None:
        renderer = MarkdownRenderer()
        table = renderer.render_table(["A", "B"], [["1", "2"], ["3", "4"]])
        assert "| A | B |" in table
        assert "| 1 | 2 |" in table
        assert "| 3 | 4 |" in table

    def test_render_table_empty_headers(self) -> None:
        renderer = MarkdownRenderer()
        assert renderer.render_table([], []) == ""

    def test_render_bullet_list(self) -> None:
        renderer = MarkdownRenderer()
        lst = renderer.render_bullet_list(["a", "b", "c"])
        assert "- a" in lst
        assert "- b" in lst
        assert "- c" in lst

    def test_render_code_block(self) -> None:
        renderer = MarkdownRenderer()
        block = renderer.render_code_block("print('hi')", "python")
        assert "```python" in block
        assert "print('hi')" in block

    def test_render_properties_table(self) -> None:
        renderer = MarkdownRenderer()
        table = renderer.render_properties_table({"Name": "Alice", "Age": "30"})
        assert "Property | Value" in table
        assert "Name" in table
        assert "Alice" in table

    def test_render_section_content(self) -> None:
        renderer = MarkdownRenderer()
        section = renderer.render_section_content("Title", "Content", 1)
        assert section.title == "Title"
        assert section.content == "Content"
        assert section.order == 1


# ---------------------------------------------------------------------------
# HTMLRenderer
# ---------------------------------------------------------------------------

class TestHTMLRenderer:
    def test_render_page(self) -> None:
        renderer = HTMLRenderer()
        page = DocumentationPage(
            title="Test",
            api_name="T",
            component_type="object",
            sections=[Section(title="Sec", content="Content", order=0)],
        )
        html = renderer.render_page(page)
        assert "<!DOCTYPE html>" in html
        assert "<title>Test</title>" in html
        assert "Sec" in html

    def test_render_page_escapes_html(self) -> None:
        renderer = HTMLRenderer()
        page = DocumentationPage(
            title="<script>alert('xss')</script>",
            sections=[Section(title="<b>bold</b>", content="<br>", order=0)],
        )
        html = renderer.render_page(page)
        assert "&lt;script&gt;" in html
        assert "&lt;b&gt;" in html

    def test_render_table(self) -> None:
        renderer = HTMLRenderer()
        html = renderer.render_table(["A", "B"], [["1", "2"]])
        assert "<table>" in html
        assert "<th>A</th>" in html
        assert "<td>1</td>" in html

    def test_render_bullet_list(self) -> None:
        renderer = HTMLRenderer()
        html = renderer.render_bullet_list(["x", "y"])
        assert "<ul>" in html
        assert "<li>x</li>" in html

    def test_render_properties_table(self) -> None:
        renderer = HTMLRenderer()
        html = renderer.render_properties_table({"K": "V"})
        assert "<th>Property</th>" in html
        assert "<td>V</td>" in html

    def test_render_code_block(self) -> None:
        renderer = HTMLRenderer()
        html = renderer.render_code_block("code", "python")
        assert "<pre>" in html
        assert "code" in html


# ---------------------------------------------------------------------------
# JSONExporter
# ---------------------------------------------------------------------------

class TestJSONExporter:
    def test_export_page(self) -> None:
        exporter = JSONExporter()
        page = DocumentationPage(id="p1", title="Test", api_name="T")
        js = exporter.export_page(page)
        assert '"title": "Test"' in js
        assert '"api_name": "T"' in js

    def test_export_report(self) -> None:
        exporter = JSONExporter()
        report = DocumentationReport(id="r1", title="R")
        js = exporter.export_report(report)
        assert '"title": "R"' in js
        assert '"id": "r1"' in js

    def test_export_section(self) -> None:
        exporter = JSONExporter()
        section = Section(title="S", content="C")
        js = exporter.export_section(section)
        assert '"title": "S"' in js

    def test_export_batch(self) -> None:
        exporter = JSONExporter()
        pages = [DocumentationPage(id="p1"), DocumentationPage(id="p2")]
        js = exporter.export_batch(pages)
        assert '"id": "p1"' in js
        assert '"id": "p2"' in js


# ---------------------------------------------------------------------------
# ExportCoordinator
# ---------------------------------------------------------------------------

class TestExportCoordinator:
    def test_export_json(self) -> None:
        json_exporter = JSONExporter()
        coord = ExportCoordinator(json_exporter)
        report = DocumentationReport(id="r1", title="R")
        request = ExportRequest(format=DocumentationFormat.JSON)
        content = coord.export(report, request)
        assert '"title": "R"' in content
        stats = coord.export_statistics()
        assert len(stats) == 1

    def test_export_markdown_report(self) -> None:
        json_exporter = JSONExporter()
        coord = ExportCoordinator(json_exporter)
        page = DocumentationPage(
            title="P", api_name="A", component_type="object",
            sections=[Section(title="S", content="C", order=0)],
        )
        report = DocumentationReport(id="r1", title="R", pages=[page],
                                      format=DocumentationFormat.MARKDOWN)
        request = ExportRequest(format=DocumentationFormat.MARKDOWN)
        content = coord.export(report, request)
        assert "R" in content
        assert "P" in content

    def test_export_html_report(self) -> None:
        json_exporter = JSONExporter()
        coord = ExportCoordinator(json_exporter)
        page = DocumentationPage(
            title="P", api_name="A", sections=[Section(title="S", content="C", order=0)],
        )
        report = DocumentationReport(id="r1", title="R", pages=[page],
                                      format=DocumentationFormat.HTML)
        request = ExportRequest(format=DocumentationFormat.HTML)
        content = coord.export(report, request)
        assert "<!DOCTYPE html>" in content
        assert "R" in content

    def test_export_pages_batch(self) -> None:
        json_exporter = JSONExporter()
        coord = ExportCoordinator(json_exporter)
        pages = [
            DocumentationPage(id="p1", title="P1"),
            DocumentationPage(id="p2", title="P2"),
        ]
        js = coord.export_pages_batch(pages, DocumentationFormat.JSON)
        assert '"id": "p1"' in js
        assert '"id": "p2"' in js

    def test_export_pages_batch_markdown(self) -> None:
        json_exporter = JSONExporter()
        coord = ExportCoordinator(json_exporter)
        pages = [DocumentationPage(title="P1", api_name="A")]
        md = coord.export_pages_batch(pages, DocumentationFormat.MARKDOWN)
        assert "P1" in md
        assert "A" in md


# ---------------------------------------------------------------------------
# DocumentationCache
# ---------------------------------------------------------------------------

class TestDocumentationCache:
    def test_get_miss(self) -> None:
        cache = DocumentationCache()
        assert cache.get("nonexistent") is None

    def test_set_and_get(self) -> None:
        cache = DocumentationCache()
        page = DocumentationPage(id="p1", title="Test")
        cache.set("key1", page)
        retrieved = cache.get("key1")
        assert retrieved is not None
        assert retrieved.id == "p1"

    def test_invalidate(self) -> None:
        cache = DocumentationCache()
        page = DocumentationPage(id="p1")
        cache.set("k", page)
        cache.invalidate("k")
        assert cache.get("k") is None

    def test_invalidate_by_type(self) -> None:
        cache = DocumentationCache()
        cache.set("k1", DocumentationPage(id="p1", component_type="object"))
        cache.set("k2", DocumentationPage(id="p2", component_type="object"))
        cache.set("k3", DocumentationPage(id="p3", component_type="field"))
        assert cache.invalidate_by_type("object") == 2
        assert cache.size() == 1

    def test_clear(self) -> None:
        cache = DocumentationCache()
        cache.set("k", DocumentationPage(id="p1"))
        cache.clear()
        assert cache.size() == 0

    def test_total_bytes(self) -> None:
        cache = DocumentationCache()
        cache.set("k", DocumentationPage(id="p1"))
        assert cache.total_bytes() > 0


# ---------------------------------------------------------------------------
# GenerationMetrics
# ---------------------------------------------------------------------------

class TestGenerationMetrics:
    def test_snapshot_empty(self) -> None:
        metrics = GenerationMetrics()
        snap = metrics.snapshot()
        assert snap.total_pages_generated == 0
        assert snap.cache_hits == 0

    def test_record_page(self) -> None:
        metrics = GenerationMetrics()
        metrics.record_page("object", 10.0)
        metrics.record_page("field", 5.0)
        snap = metrics.snapshot()
        assert snap.total_pages_generated == 2
        assert 7.0 <= snap.avg_generation_time_ms <= 8.0

    def test_record_report(self) -> None:
        metrics = GenerationMetrics()
        metrics.record_report("dependency")
        snap = metrics.snapshot()
        assert snap.total_reports_generated == 1

    def test_record_cache_hit(self) -> None:
        metrics = GenerationMetrics()
        metrics.record_cache_hit()
        snap = metrics.snapshot()
        assert snap.cache_hits == 1

    def test_record_error(self) -> None:
        metrics = GenerationMetrics()
        metrics.record_error()
        snap = metrics.snapshot()
        assert snap.total_errors == 1

    def test_record_export(self) -> None:
        metrics = GenerationMetrics()
        metrics.record_export()
        snap = metrics.snapshot()
        assert snap.total_exports == 1


# ---------------------------------------------------------------------------
# DocumentationGenerator
# ---------------------------------------------------------------------------

class TestDocumentationGenerator:
    def test_generate_single_component(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "object:Account")
        assert page is not None
        assert page.component_key == "object:Account"
        assert len(page.sections) > 0
        overviews = [s for s in page.sections if s.section_type == SectionType.OVERVIEW]
        assert len(overviews) > 0

    def test_generate_single_not_found(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "object:NonExistent")
        assert "Not Found" in page.title

    def test_generate_produces_report(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        request = GenerateRequest(
            component_keys=["object:Account", "field:Account.Name"],
            report_type=ReportType.COMPONENT,
        )
        report = gen.generate(sample_graph, request)
        assert len(report.pages) == 2

    def test_generate_with_format_html(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        request = GenerateRequest(
            component_keys=["object:Account"],
            format=DocumentationFormat.HTML,
        )
        report = gen.generate(sample_graph, request)
        assert report.format == DocumentationFormat.HTML

    def test_generate_from_nodes(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        nodes = [sample_graph.get_node("object:Account")]
        pages = gen.generate_from_nodes(nodes, sample_graph)
        assert len(pages) == 1

    def test_generate_section_types(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "object:Account")
        types = {s.section_type for s in page.sections}
        assert SectionType.OVERVIEW in types

    def test_generate_field_page(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "field:Account.Name")
        assert page.component_type == "field"

    def test_generate_flow_page(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "flow:AccountFlow")
        assert page.component_type == "flow"

    def test_generate_apex_page(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "apex_class:AccountService")
        assert page.component_type == "apex_class"

    def test_generate_word_count(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(sample_graph, "object:Account")
        assert page.word_count > 0

    def test_generate_respects_include_sections(self, sample_graph: Graph) -> None:
        gen = DocumentationGenerator()
        page = gen.generate_single(
            sample_graph, "object:Account",
            include_sections=["overview"],
        )
        types = {s.section_type for s in page.sections}
        assert types == {SectionType.OVERVIEW}


# ---------------------------------------------------------------------------
# DocumentationEngine
# ---------------------------------------------------------------------------

class TestDocumentationEngine:
    def test_engine_creates_generator(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        assert engine.graph is not None

    def test_generate_component(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        request = GenerateRequest(
            component_keys=["object:Account"],
            report_type=ReportType.COMPONENT,
        )
        report = engine.generate(request)
        assert len(report.pages) >= 1

    def test_generate_single_page(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        page = engine.generate_single("object:Account")
        assert page.component_key == "object:Account"

    def test_generate_single_cached(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        engine.generate_single("object:Account")
        page2 = engine.generate_single("object:Account")
        assert page2.component_key == "object:Account"

    def test_dependency_tree(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.dependency_tree("object:Account")
        assert report.report_type == ReportType.DEPENDENCY

    def test_reverse_dependency_tree(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.reverse_dependency_tree("field:Account.Name")
        assert report.report_type == ReportType.DEPENDENCY

    def test_component_references(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.component_references("object:Account")
        assert report.report_type == ReportType.DEPENDENCY

    def test_graph_summary(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.graph_summary()
        assert report.pages is not None

    def test_circular_dependencies(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.circular_dependencies()
        assert report.title is not None

    def test_organization_overview(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.organization_overview()
        assert report.report_type == ReportType.ARCHITECTURE

    def test_component_inventory(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.component_inventory()
        assert report.report_type == ReportType.ARCHITECTURE

    def test_component_inventory_filtered(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.component_inventory(component_type="object")
        assert report.report_type == ReportType.ARCHITECTURE

    def test_relationship_overview(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.relationship_overview()
        assert report.report_type == ReportType.ARCHITECTURE

    def test_metadata_report(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.metadata_report()
        assert report.report_type == ReportType.METADATA

    def test_impact_report(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.impact_report("object:Account")
        assert report.report_type == ReportType.IMPACT

    def test_export_report(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        report = engine.generate(
            GenerateRequest(component_keys=["object:Account"]),
        )
        content = engine.export_report(report, DocumentationFormat.JSON)
        assert '"title"' in content

    def test_statistics(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        engine.generate_single("object:Account")
        stats = engine.documentation_statistics()
        assert stats.total_pages_generated >= 1

    def test_cache_operations(self, sample_graph: Graph) -> None:
        mock = MagicMock()
        type(mock).graph = PropertyMock(return_value=sample_graph)
        engine = DocumentationEngine(graph_engine=mock)
        assert engine.cache_size() == 0
        engine.generate_single("object:Account")
        assert engine.cache_size() >= 1
        engine.clear_cache()
        assert engine.cache_size() == 0


# ---------------------------------------------------------------------------
# DependencyReportGenerator
# ---------------------------------------------------------------------------

class TestDependencyReportGenerator:
    def test_dependency_tree(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_dependency_tree(sample_graph, "object:Account")
        assert len(report.pages) > 0

    def test_reverse_dependency_tree(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_reverse_dependency_tree(sample_graph, "field:Account.Name")
        assert len(report.pages) > 0

    def test_component_references(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_component_references(sample_graph, "object:Account")
        assert report.statistics is not None

    def test_graph_summary(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_graph_summary(sample_graph)
        assert report.statistics is not None
        assert report.statistics["total_nodes"] > 0

    def test_circular_dependency_report(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_circular_dependency_report(sample_graph)
        assert report.title is not None

    def test_component_references_nonexistent(self, sample_graph: Graph) -> None:
        gen = DependencyReportGenerator()
        report = gen.generate_component_references(sample_graph, "object:Nope")
        assert "not found" in report.title.lower()


# ---------------------------------------------------------------------------
# ArchitectureReportGenerator
# ---------------------------------------------------------------------------

class TestArchitectureReportGenerator:
    def test_organization_overview(self, sample_graph: Graph) -> None:
        gen = ArchitectureReportGenerator()
        report = gen.generate_organization_overview(sample_graph)
        assert len(report.pages) > 0

    def test_component_inventory(self, sample_graph: Graph) -> None:
        gen = ArchitectureReportGenerator()
        report = gen.generate_component_inventory(sample_graph)
        assert report.statistics["total_components"] > 0

    def test_component_inventory_filtered(self, sample_graph: Graph) -> None:
        gen = ArchitectureReportGenerator()
        report = gen.generate_component_inventory(sample_graph, component_type="object")
        assert report.statistics["total_components"] > 0

    def test_relationship_overview(self, sample_graph: Graph) -> None:
        gen = ArchitectureReportGenerator()
        report = gen.generate_relationship_overview(sample_graph)
        assert report.statistics is not None
        assert report.statistics["total_relationships"] > 0


# ---------------------------------------------------------------------------
# MetadataReportGenerator
# ---------------------------------------------------------------------------

class TestMetadataReportGenerator:
    def test_generate_metadata_report(self, sample_graph: Graph) -> None:
        gen = MetadataReportGenerator()
        report = gen.generate_metadata_report(sample_graph)
        assert report.report_type == ReportType.METADATA
        assert report.statistics["total"] > 0


# ---------------------------------------------------------------------------
# ImpactReportGenerator
# ---------------------------------------------------------------------------

class TestDocumentationImpactReportGenerator:
    def test_generate_impact_report(self, sample_graph: Graph) -> None:
        gen = ImpactReportGenerator()
        report = gen.generate_impact_report(sample_graph, "object:Account")
        assert report.report_type == ReportType.IMPACT
        assert report.statistics is not None
        assert "total_affected" in report.statistics

    def test_generate_impact_report_unknown(self, sample_graph: Graph) -> None:
        gen = ImpactReportGenerator()
        report = gen.generate_impact_report(sample_graph, "object:NonExistent")
        assert report.statistics is not None
