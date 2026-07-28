from __future__ import annotations

from sfir_backend.application.pipeline.mapper.i_mapping_strategy import IMappingStrategy
from sfir_backend.domain.canonical.reporting import MetadataDashboard, MetadataReport
from sfir_backend.domain.metadata.analytics import Dashboard, Report


class ReportStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Report)

    def map(self, parsed: object) -> MetadataReport:
        r = parsed
        return MetadataReport(
            api_name=r.name,
            label=r.label or r.name,
            object_api_name=r.object_type or "",
            report_type=r.report_type or "Tabular",
            metadata_properties={
                "component_id": r.component_id,
                "description": r.description,
                "columns": r.columns,
                "filters": r.filters,
                "groupings": r.groupings,
                "chart": r.chart,
                "format": r.format,
                "params": r.params,
            },
        )


class DashboardStrategy(IMappingStrategy):
    def can_handle(self, parsed: object) -> bool:
        return isinstance(parsed, Dashboard)

    def map(self, parsed: object) -> MetadataDashboard:
        d = parsed
        return MetadataDashboard(
            api_name=d.name,
            label=d.label or d.name,
            dashboard_type=d.dashboard_type or "Specified",
            metadata_properties={
                "component_id": d.component_id,
                "description": d.description,
                "background": d.background,
                "layout": d.layout,
                "left_section": d.left_section,
                "middle_section": d.middle_section,
                "right_section": d.right_section,
            },
        )
