from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LightingComponentBundle:
    name: str
    api_version: int = 0
    component_id: str | None = None
    description: str | None = None
    target_configs: list[dict] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    is_exposed: bool = False
