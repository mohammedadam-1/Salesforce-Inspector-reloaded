from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentQueryRequest:
    query: str
    organization_id: str
    history: list[dict[str, str]] | None = None


@dataclass
class AgentQueryResponse:
    response: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
