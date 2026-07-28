from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FlowVariable:
    name: str
    data_type: str = "String"
    is_input: bool = False
    is_output: bool = False
    default_value: str | None = None
    object_type: str | None = None


@dataclass
class FlowStage:
    name: str
    label: str = ""
    is_active: bool = True
    order: int = 0


@dataclass
class FlowElement:
    name: str
    element_type: str = ""
    label: str = ""
    connector: str | None = None
    object_references: list[str] = field(default_factory=list)
    field_references: list[str] = field(default_factory=list)
    formula: str | None = None
    assignment_items: list[dict] = field(default_factory=list)
    filters: list[dict] = field(default_factory=list)
    outcome_actions: list[str] = field(default_factory=list)


@dataclass
class Flow:
    name: str
    label: str = ""
    description: str | None = None
    process_type: str = "Flow"
    status: str = "Draft"
    component_id: str | None = None
    variables: list[FlowVariable] = field(default_factory=list)
    stages: list[FlowStage] = field(default_factory=list)
    elements: list[FlowElement] = field(default_factory=list)
    record_creates: list[str] = field(default_factory=list)
    record_updates: list[str] = field(default_factory=list)
    record_deletes: list[str] = field(default_factory=list)
    subflows: list[str] = field(default_factory=list)
    interview_label: str | None = None
    run_in_mode: str = "SystemModeWithoutSharing"
    api_version: int | None = None
