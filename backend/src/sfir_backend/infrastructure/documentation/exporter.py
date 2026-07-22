from __future__ import annotations

import json
from typing import Any

from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    ExportRequest,
    Section,
)


class JSONExporter:
    def export_page(self, page: DocumentationPage) -> str:
        return page.model_dump_json(indent=2)

    def export_report(self, report: DocumentationReport) -> str:
        return report.model_dump_json(indent=2)

    def export_section(self, section: Section) -> str:
        return section.model_dump_json(indent=2)

    def export_batch(self, items: list[Any]) -> str:
        return json.dumps(
            [item.model_dump() if hasattr(item, "model_dump") else item for item in items],
            indent=2,
            default=str,
        )


class ExportCoordinator:
    def __init__(self, json_exporter: JSONExporter) -> None:
        self._json = json_exporter
        self._exports: list[dict[str, Any]] = []

    def export(
        self,
        report: DocumentationReport,
        request: ExportRequest,
    ) -> str:
        if request.format == DocumentationFormat.JSON:
            content = self._json.export_report(report)
        elif report.format == DocumentationFormat.MARKDOWN:
            content = self._format_markdown_report(report)
        elif report.format == DocumentationFormat.HTML:
            content = self._format_html_report(report)
        else:
            content = self._json.export_report(report)

        self._exports.append({
            "report_id": report.id,
            "format": request.format.value,
            "size_bytes": len(content.encode("utf-8")),
        })
        return content

    def export_pages_batch(
        self,
        pages: list[DocumentationPage],
        format: DocumentationFormat = DocumentationFormat.JSON,
    ) -> str:
        if format == DocumentationFormat.JSON:
            return self._json.export_batch(pages)
        lines: list[str] = []
        for page in pages:
            if format == DocumentationFormat.MARKDOWN:
                from sfir_backend.infrastructure.documentation.renderers import MarkdownRenderer
                lines.append(MarkdownRenderer().render_page(page))
                lines.append("\n---\n")
            elif format == DocumentationFormat.HTML:
                from sfir_backend.infrastructure.documentation.renderers import HTMLRenderer
                lines.append(HTMLRenderer().render_page(page))
        return "\n".join(lines)

    def export_statistics(self) -> list[dict[str, Any]]:
        return list(self._exports)

    def _format_markdown_report(self, report: DocumentationReport) -> str:
        from sfir_backend.infrastructure.documentation.renderers import MarkdownRenderer
        renderer = MarkdownRenderer()
        parts: list[str] = []
        parts.append(f"# {report.title}")
        parts.append("")
        parts.append(f"**Report Type:** {report.report_type.value}  ")
        parts.append(f"**Pages:** {len(report.pages)}  ")
        parts.append(f"**Generated:** {report.generated_at.isoformat()}  ")
        parts.append("")
        parts.append("---")
        parts.append("")
        for page in report.pages:
            parts.append(renderer.render_page(page))
        return "\n".join(parts)

    def _format_html_report(self, report: DocumentationReport) -> str:
        from sfir_backend.infrastructure.documentation.renderers import HTMLRenderer
        renderer = HTMLRenderer()
        parts: list[str] = []
        parts.extend([
            "<!DOCTYPE html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="UTF-8">',
            f"<title>{report.title}</title>",
            renderer.CSS,
            "</head>",
            "<body>",
            f"<h1>{report.title}</h1>",
            f'<p class="meta">Report Type: {report.report_type.value}'
            f' &middot; Pages: {len(report.pages)}'
            f' &middot; Generated: {report.generated_at.isoformat()}</p>',
            "<hr>",
        ])
        for page in report.pages:
            parts.append(renderer.render_page(page))
        parts.extend(["</body>", "</html>"])
        return "\n".join(parts)
