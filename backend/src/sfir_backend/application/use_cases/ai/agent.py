from __future__ import annotations

from typing import Any

from sfir_backend.application.use_cases.ai.tools import AgentTool, ToolRegistry
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.domain.graph.models import DependencyGraph
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
)


class QueryMetadataTool(AgentTool):
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service
        self._graph: DependencyGraph | None = None

    def set_graph(self, graph: DependencyGraph) -> None:
        self._graph = graph

    @property
    def name(self) -> str:
        return "query_metadata"

    @property
    def description(self) -> str:
        return "Query metadata components by type and name pattern"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "description": "Metadata type (e.g. ApexClass, CustomObject, Profile)",
                },
                "name_pattern": {
                    "type": "string",
                    "description": "Name pattern to search (e.g. Account, *Controller)",
                },
            },
            "required": ["component_type"],
        }

    async def execute(
        self,
        component_type: str,
        name_pattern: str = "",
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        if not self._graph:
            return "Graph not available. Build the graph first."
        if not component_type:
            return "component_type is required"
        results: list[str] = []
        for node in self._graph.nodes.values():
            if node.component_type == component_type:
                if name_pattern:
                    import fnmatch
                    if fnmatch.fnmatch(node.component_name, name_pattern):
                        results.append(str(node))
                else:
                    results.append(str(node))
        if not results:
            return f"No {component_type} components found matching '{name_pattern}'"
        lines = [f"Found {len(results)} {component_type} components:"]
        lines.extend(sorted(results)[:50])
        return "\n".join(lines)


class AnalyzeDependenciesTool(AgentTool):
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service
        self._graph: DependencyGraph | None = None

    def set_graph(self, graph: DependencyGraph) -> None:
        self._graph = graph

    @property
    def name(self) -> str:
        return "analyze_dependencies"

    @property
    def description(self) -> str:
        return "Analyze dependencies for a given metadata component"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "component_type": {"type": "string"},
                "component_name": {"type": "string"},
                "depth": {"type": "integer", "default": 1},
            },
            "required": ["component_type", "component_name"],
        }

    async def execute(
        self,
        component_type: str,
        component_name: str,
        depth: int = 1,
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        if not self._graph:
            return "Graph not available. Build the graph first."
        deps = await self._graph_service.get_node_dependencies(
            self._graph, component_type, component_name, depth,
        )
        if not deps.get("node"):
            return f"Component '{component_type}:{component_name}' not found in graph"
        lines = [f"Dependencies for {component_type}:{component_name}:"]
        if deps["upstream"]:
            lines.append(f"  Uses ({len(deps['upstream'])}):")
            for d in deps["upstream"]:
                lines.append(f"    - {d['component_type']}:{d['component_name']}")
        if deps["downstream"]:
            lines.append(f"  Used by ({len(deps['downstream'])}):")
            for d in deps["downstream"]:
                lines.append(f"    - {d['component_type']}:{d['component_name']}")
        if not deps["upstream"] and not deps["downstream"]:
            lines.append("  No dependencies found")
        return "\n".join(lines)


class FindImpactTool(AgentTool):
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service
        self._graph: DependencyGraph | None = None

    def set_graph(self, graph: DependencyGraph) -> None:
        self._graph = graph

    @property
    def name(self) -> str:
        return "find_impact"

    @property
    def description(self) -> str:
        return "Find all components impacted by changes to a given component"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "component_type": {"type": "string"},
                "component_name": {"type": "string"},
                "max_depth": {"type": "integer", "default": 3},
            },
            "required": ["component_type", "component_name"],
        }

    async def execute(
        self,
        component_type: str,
        component_name: str,
        max_depth: int = 3,
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        if not self._graph:
            return "Graph not available. Build the graph first."
        impacted = await self._graph_service.find_impact(
            self._graph, component_type, component_name, max_depth,
        )
        if not impacted:
            return f"No impacted components found for '{component_type}:{component_name}'"
        lines = [f"Impact analysis for {component_type}:{component_name} (depth={max_depth}):"]
        for item in impacted:
            lines.append(f"  - {item['component_type']}:{item['component_name']}")
        return "\n".join(lines)


class GraphSummaryTool(AgentTool):
    def __init__(self, graph_service: GraphService) -> None:
        self._graph_service = graph_service
        self._graph: DependencyGraph | None = None

    def set_graph(self, graph: DependencyGraph) -> None:
        self._graph = graph

    @property
    def name(self) -> str:
        return "graph_summary"

    @property
    def description(self) -> str:
        return "Get a summary of the entire metadata dependency graph"

    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    async def execute(
        self,
        request_context: RequestContext | None = None,
    ) -> str:
        _ = request_context
        if not self._graph:
            return "Graph not available. Build the graph first."
        summary = await self._graph_service.graph_summary(self._graph)
        lines = [
            "Metadata Dependency Graph Summary:",
            f"  Nodes: {summary['node_count']}",
            f"  Edges: {summary['edge_count']}",
            f"  Cycles: {summary['cycles']}",
            "  Component types:",
        ]
        for ctype, count in sorted(summary["component_types"].items()):
            lines.append(f"    {ctype}: {count}")
        return "\n".join(lines)


class AgentService:
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        tool_registry: ToolRegistry,
        graph_service: GraphService,
    ) -> None:
        self._llm = llm_provider
        self._tools = tool_registry
        self._graph_service = graph_service

    async def process_query(
        self,
        query: str,
        _organization_id: Any = None,
        graph: DependencyGraph | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if graph is None:
            graph = DependencyGraph()

        for tool in self._tools.list_tools():
            if hasattr(tool, "set_graph"):
                tool.set_graph(graph)

        messages = [
            LLMMessage(
                role="system",
                content=(
                    "You are a Salesforce metadata expert assistant. "
                    "You have access to tools that can query metadata components, "
                    "analyze dependencies, find impact, and summarize the metadata graph. "
                    "Answer questions clearly and concisely based on the data available."
                ),
            ),
        ]
        if history:
            for msg in history:
                messages.append(LLMMessage(role=msg["role"], content=msg["content"]))

        messages.append(LLMMessage(role="user", content=query))

        response = await self._llm.chat_with_tools(
            messages=messages,
            tools=self._tools.to_definitions(),
        )
        return {
            "response": response.content,
            "usage": response.usage,
            "finish_reason": response.finish_reason,
        }
