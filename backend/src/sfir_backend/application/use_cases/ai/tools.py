from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sfir_backend.infrastructure.llm.providers.base import ToolDefinition


class AgentTool(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        ...

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def execute(self, **kwargs: Any) -> str:
        ...

    def to_tool_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters(),
        )


@dataclass
class ToolRegistry:
    _tools: dict[str, AgentTool] = field(default_factory=dict)

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def to_definitions(self) -> list[ToolDefinition]:
        return [t.to_tool_definition() for t in self._tools.values()]

    async def execute(self, name: str, **kwargs: Any) -> str:
        tool = self.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found"
        return await tool.execute(**kwargs)
