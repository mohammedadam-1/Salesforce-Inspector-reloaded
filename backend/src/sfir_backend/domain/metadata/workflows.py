from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowRule:
    name: str
    object_type: str = ""
    active: bool = True
    description: str | None = None
    formula: str = ""
    actions: list[WorkflowAction] = field(default_factory=list)


@dataclass
class WorkflowAction:
    name: str
    action_type: str = ""
    component_id: str | None = None
    description: str | None = None


@dataclass
class WorkflowAlert:
    name: str
    description: str | None = None
    cc_emails: list[str] = field(default_factory=list)
    bcc_emails: list[str] = field(default_factory=list)
    sender_email: str | None = None
    sender_type: str = "CurrentUser"
    template: str = ""
    protected: bool = False


@dataclass
class WorkflowFieldUpdate:
    name: str
    field: str = ""
    object_type: str = ""
    operation: str = ""
    value: str | None = None
    formula: str | None = None
    reevaluate_on_change: bool = False
    lookup_value: str | None = None


@dataclass
class WorkflowOutboundMessage:
    name: str
    description: str | None = None
    endpoint_url: str = ""
    fields: list[str] = field(default_factory=list)
    include_session_id: bool = False
    integration_user: str = ""
    protocol: str = "SOAP"
    use_https: bool = True


@dataclass
class WorkflowTask:
    name: str
    assigned_to: str = ""
    assigned_to_type: str = "user"
    description: str | None = None
    due_date_offset: int = 0
    notify_assignee: bool = True
    priority: str = "Normal"
    protected: bool = False
    recurrence_type: str | None = None
    status: str = "NotStarted"
    subject: str = ""
    send_email: bool = False
