from __future__ import annotations

from typing import Any

from sfir_backend.domain.canonical import MetadataDashboard, MetadataReport
from sfir_backend.infrastructure.parsers.base import BaseParser, ParserContext


class ReportParser(BaseParser):
    metadata_type = "report"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataReport:
        _ = context
        return MetadataReport(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            object_api_name=data.get("object_api_name", ""),
            report_type=data.get("reportType", data.get("report_type", "Tabular")),
            report_format=data.get("reportFormat", data.get("report_format", "")),
            folder_name=data.get("folderName", data.get("folder_name")),
            params=data.get("params", {}),
        )


class DashboardParser(BaseParser):
    metadata_type = "dashboard"

    def _parse(
        self,
        data: dict[str, Any],
        context: ParserContext | None = None,
    ) -> MetadataDashboard:
        _ = context
        return MetadataDashboard(
            api_name=data.get("fullName", ""),
            label=data.get("label", ""),
            description=data.get("description"),
            folder_name=data.get("folderName", data.get("folder_name")),
            background_fitness=data.get(
                "backgroundFitness", data.get("background_fitness", "None"),
            ),
            dashboard_type=data.get(
                "dashboardType", data.get("dashboard_type", "Specified"),
            ),
            dashboard_result=data.get(
                "dashboardResult", data.get("dashboard_result"),
            ),
            components=data.get("components", []),
            left_section=data.get("leftSection", data.get("left_section", [])),
            middle_section=data.get("middleSection", data.get("middle_section", [])),
            right_section=data.get("rightSection", data.get("right_section", [])),
        )
