from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Queue:
    name: str
    label: str = ""
    component_id: str | None = None
    queue_sobject: list[dict] = field(default_factory=list)
    queue_members: list[dict] = field(default_factory=list)
    email: str | None = None


@dataclass
class Role:
    name: str
    label: str = ""
    component_id: str | None = None
    parent_role: str | None = None
    contact_access: str = "Read"
    opportunity_access: str = "Read"
    case_access: str = "Read"


@dataclass
class SharingRule:
    name: str
    shared_object: str = ""
    sharing_rule_type: str = ""


@dataclass
class SharingCriteriaRule:
    name: str
    shared_object: str = ""
    access_level: str = "Read"
    criteria: list[dict] = field(default_factory=list)
    label: str = ""
    description: str | None = None


@dataclass
class SharingOwnerRule:
    name: str
    shared_object: str = ""
    access_level: str = "Read"
    label: str = ""
    description: str | None = None
    shared_from: str | None = None
