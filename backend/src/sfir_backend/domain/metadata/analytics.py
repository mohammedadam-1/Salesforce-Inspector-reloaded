from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Report:
    name: str
    label: str = ""
    object_type: str = ""
    report_type: str = "Tabular"
    component_id: str | None = None
    description: str | None = None
    columns: list[dict] = field(default_factory=list)
    filters: list[dict] = field(default_factory=list)
    groupings: list[dict] = field(default_factory=list)
    chart: dict | None = None
    format: str = ""
    params: list[dict] = field(default_factory=list)


@dataclass
class DashboardComponent:
    name: str
    component_type: str = ""
    object_type: str | None = None
    report_name: str | None = None
    filters: list[dict] = field(default_factory=list)
    chart_settings: dict | None = None


@dataclass
class Dashboard:
    name: str
    label: str = ""
    dashboard_type: str = "SpecifiedUser"
    component_id: str | None = None
    description: str | None = None
    components: list[DashboardComponent] = field(default_factory=list)
    background: str = ""
    layout: str = ""
    left_section: str = ""
    middle_section: str = ""
    right_section: str = ""
