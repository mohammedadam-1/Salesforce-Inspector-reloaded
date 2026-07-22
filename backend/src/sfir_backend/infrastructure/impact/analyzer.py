from __future__ import annotations

from collections import deque

from sfir_backend.domain.impact.models import (
    AffectedComponent,
    ChangeType,
    ImpactPath,
    ImpactSeverity,
    ImpactStatus,
)
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine


class DependencyImpactAnalyzer:
    def __init__(self, graph_engine: DependencyGraphEngine) -> None:
        self._graph_engine = graph_engine

    def find_impacted(
        self,
        component_key: str,
        change_type: ChangeType = ChangeType.MODIFY,
        max_depth: int = 5,
        include_types: list[str] | None = None,
        exclude_types: list[str] | None = None,
    ) -> tuple[list[AffectedComponent], list[ImpactPath]]:
        graph = self._graph_engine.graph
        affected: list[AffectedComponent] = []
        paths: list[ImpactPath] = []
        visited: set[str] = set()

        if component_key not in graph.nodes:
            return [], []

        graph.get_node(component_key)

        queue: deque[tuple[str, str, int, list[str]]] = deque()
        queue.append((component_key, "", 0, [component_key]))
        visited.add(component_key)

        while queue:
            current, edge_type, depth, path = queue.popleft()
            if depth >= max_depth:
                continue
            if current != component_key:
                current_node = graph.get_node(current)
                ctype = "unknown"
                cname = ""
                if current_node:
                    ctype = current_node.node_type.value if current_node.node_type else "unknown"
                    cname = current_node.api_name

                if (include_types and ctype not in include_types) or (exclude_types and ctype in exclude_types):
                    pass
                else:
                    severity = self._determine_severity(depth, change_type)
                    status = self._determine_status(depth, change_type, severity)
                    dep_path = ImpactPath(
                        nodes=list(path),
                        edges=[edge_type] if edge_type else [],
                        total_depth=depth,
                    )
                    affected.append(AffectedComponent(
                        component_key=current,
                        name=cname,
                        component_type=ctype,
                        dependency_depth=depth,
                        severity=severity,
                        status=status,
                        change_type=change_type,
                    ))
                    paths.append(dep_path)

            for edge in graph.get_outgoing_edges(current):
                neighbor = edge.target_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((
                        neighbor,
                        edge.edge_type.value if edge.edge_type else "",
                        depth + 1,
                        [*path, neighbor],
                    ))

            for edge in graph.get_incoming_edges(current):
                neighbor = edge.source_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((
                        neighbor,
                        edge.edge_type.value if edge.edge_type else "",
                        depth + 1,
                        [*path, neighbor],
                    ))

        return affected, paths

    def _determine_severity(self, depth: int, change_type: ChangeType) -> ImpactSeverity:
        if change_type == ChangeType.DELETE:
            if depth <= 1:
                return ImpactSeverity.CRITICAL
            if depth <= 2:
                return ImpactSeverity.HIGH
            if depth <= 3:
                return ImpactSeverity.MEDIUM
            return ImpactSeverity.LOW
        if change_type == ChangeType.RENAME:
            if depth <= 1:
                return ImpactSeverity.HIGH
            if depth <= 2:
                return ImpactSeverity.MEDIUM
            return ImpactSeverity.LOW
        if depth <= 1:
            return ImpactSeverity.MEDIUM
        return ImpactSeverity.LOW

    def _determine_status(
        self,
        depth: int,
        change_type: ChangeType,
        severity: ImpactSeverity,
    ) -> ImpactStatus:
        if severity == ImpactSeverity.CRITICAL:
            return ImpactStatus.BLOCKING
        if severity == ImpactSeverity.HIGH and change_type == ChangeType.DELETE:
            return ImpactStatus.WARNING
        return ImpactStatus.SAFE
