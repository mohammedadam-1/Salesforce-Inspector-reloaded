from __future__ import annotations

import time
from typing import Any

from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    ExportRequest,
    GenerateRequest,
    GenerationMetricsSnapshot,
    ReportType,
)
from sfir_backend.domain.graph.models import Graph
from sfir_backend.infrastructure.documentation.cache import DocumentationCache
from sfir_backend.infrastructure.documentation.exporter import (
    ExportCoordinator,
    JSONExporter,
)
from sfir_backend.infrastructure.documentation.generator import (
    DocumentationGenerator,
)
from sfir_backend.infrastructure.documentation.metrics import GenerationMetrics
from sfir_backend.infrastructure.documentation.reports import (
    ArchitectureReportGenerator,
    DependencyReportGenerator,
    ImpactReportGenerator,
    MetadataReportGenerator,
)


class DocumentationEngine:
    def __init__(
        self,
        graph_engine: Any = None,
        search_engine: Any = None,
    ) -> None:
        self._graph_engine = graph_engine
        self._search_engine = search_engine
        self._generator = DocumentationGenerator()
        self._dependency_reports = DependencyReportGenerator()
        self._architecture_reports = ArchitectureReportGenerator()
        self._metadata_reports = MetadataReportGenerator()
        self._impact_reports = ImpactReportGenerator()
        self._json_exporter = JSONExporter()
        self._export_coordinator = ExportCoordinator(self._json_exporter)
        self._cache = DocumentationCache()
        self._metrics = GenerationMetrics()

    @property
    def graph(self) -> Graph:
        if self._graph_engine is not None and hasattr(self._graph_engine, "graph"):
            return self._graph_engine.graph
        return Graph()

    @property
    def metrics(self) -> GenerationMetrics:
        return self._metrics

    def generate(self, request: GenerateRequest) -> DocumentationReport:
        start = time.time()
        graph = self.graph
        if request.report_type == ReportType.COMPONENT:
            report = self._generator.generate(graph, request)
        elif request.report_type == ReportType.DEPENDENCY:
            report = self._generate_dependency_report(graph, request)
        elif request.report_type == ReportType.ARCHITECTURE:
            report = self._generate_architecture_report(graph, request)
        elif request.report_type == ReportType.METADATA:
            report = self._metadata_reports.generate_metadata_report(graph)
        elif request.report_type == ReportType.IMPACT:
            report = self._generate_impact_report(graph, request)
        else:
            report = self._generator.generate(graph, request)

        report.took_ms = (time.time() - start) * 1000
        self._metrics.record_report(request.report_type.value)
        for page in report.pages:
            self._metrics.record_page(
                page.component_type or "unknown", report.took_ms / max(len(report.pages), 1),
            )
            cache_key = f"{request.format.value}:{page.component_key}"
            self._cache.set(cache_key, page, ttl=300)
        return report

    def generate_single(
        self,
        component_key: str,
        format: DocumentationFormat = DocumentationFormat.MARKDOWN,
    ) -> DocumentationPage:
        cache_key = f"{format.value}:{component_key}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._metrics.record_cache_hit()
            return cached

        self._metrics.record_cache_miss()
        graph = self.graph
        start = time.time()
        page = self._generator.generate_single(graph, component_key, format)
        elapsed = (time.time() - start) * 1000
        self._metrics.record_page(page.component_type or "unknown", elapsed)
        self._cache.set(cache_key, page, ttl=300)
        return page

    def export(self, report: DocumentationReport, request: ExportRequest) -> str:
        content = self._export_coordinator.export(report, request)
        self._metrics.record_export()
        return content

    def export_report(
        self,
        report: DocumentationReport,
        format: DocumentationFormat = DocumentationFormat.JSON,
    ) -> str:
        request = ExportRequest(report_ids=[report.id], format=format)
        return self.export(report, request)

    def dependency_tree(self, component_key: str) -> DocumentationReport:
        graph = self.graph
        return self._dependency_reports.generate_dependency_tree(graph, component_key)

    def reverse_dependency_tree(self, component_key: str) -> DocumentationReport:
        graph = self.graph
        return self._dependency_reports.generate_reverse_dependency_tree(
            graph, component_key,
        )

    def component_references(self, component_key: str) -> DocumentationReport:
        graph = self.graph
        return self._dependency_reports.generate_component_references(
            graph, component_key,
        )

    def graph_summary(self) -> DocumentationReport:
        graph = self.graph
        return self._dependency_reports.generate_graph_summary(graph)

    def circular_dependencies(self) -> DocumentationReport:
        graph = self.graph
        return self._dependency_reports.generate_circular_dependency_report(graph)

    def organization_overview(self) -> DocumentationReport:
        graph = self.graph
        return self._architecture_reports.generate_organization_overview(graph)

    def component_inventory(
        self,
        component_type: str | None = None,
    ) -> DocumentationReport:
        graph = self.graph
        return self._architecture_reports.generate_component_inventory(
            graph, component_type,
        )

    def relationship_overview(self) -> DocumentationReport:
        graph = self.graph
        return self._architecture_reports.generate_relationship_overview(graph)

    def metadata_report(self) -> DocumentationReport:
        graph = self.graph
        return self._metadata_reports.generate_metadata_report(graph)

    def impact_report(self, component_key: str) -> DocumentationReport:
        graph = self.graph
        return self._impact_reports.generate_impact_report(graph, component_key)

    def documentation_statistics(self) -> GenerationMetricsSnapshot:
        return self._metrics.snapshot()

    def clear_cache(self) -> None:
        self._cache.clear()

    def cache_size(self) -> int:
        return self._cache.size()

    def _generate_dependency_report(
        self,
        graph: Graph,
        request: GenerateRequest,
    ) -> DocumentationReport:
        all_pages: list[DocumentationPage] = []
        for key in request.component_keys:
            report = self._dependency_reports.generate_component_references(graph, key)
            all_pages.extend(report.pages)
        return DocumentationReport(
            title=f"Dependency Report: {len(request.component_keys)} component(s)",
            report_type=ReportType.DEPENDENCY,
            pages=all_pages,
        )

    def _generate_architecture_report(
        self,
        graph: Graph,
        _request: GenerateRequest,
    ) -> DocumentationReport:
        overview = self._architecture_reports.generate_organization_overview(graph)
        return overview

    def _generate_impact_report(
        self,
        graph: Graph,
        request: GenerateRequest,
    ) -> DocumentationReport:
        all_pages: list[DocumentationPage] = []
        for key in request.component_keys:
            report = self._impact_reports.generate_impact_report(graph, key)
            all_pages.extend(report.pages)
        return DocumentationReport(
            title=f"Impact Report: {len(request.component_keys)} component(s)",
            report_type=ReportType.IMPACT,
            pages=all_pages,
        )
