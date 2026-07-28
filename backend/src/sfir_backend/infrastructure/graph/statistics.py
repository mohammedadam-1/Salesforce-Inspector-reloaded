from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import Graph


class GraphStatistics:
    def node_count_by_type(self, graph: Graph) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in graph.nodes.values():
            type_str = node.node_type.value
            counts[type_str] = counts.get(type_str, 0) + 1
        return counts

    def edge_count_by_type(self, graph: Graph) -> dict[str, int]:
        counts: dict[str, int] = {}
        for edge in graph.edges.values():
            type_str = edge.edge_type.value
            counts[type_str] = counts.get(type_str, 0) + 1
        return counts

    def avg_degree(self, graph: Graph) -> float:
        if graph.node_count == 0:
            return 0.0
        total_degree = 0
        for node_key in graph.nodes:
            out_deg = len(graph.get_outgoing_edges(node_key))
            in_deg = len(graph.get_incoming_edges(node_key))
            total_degree += out_deg + in_deg
        return total_degree / graph.node_count

    def density(self, graph: Graph) -> float:
        n = graph.node_count
        if n <= 1:
            return 0.0
        max_edges = n * (n - 1)
        return graph.edge_count / max_edges if max_edges > 0 else 0.0

    def snapshot(self, graph: Graph) -> dict[str, Any]:
        return {
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "avg_degree": self.avg_degree(graph),
            "density": self.density(graph),
            "node_types": self.node_count_by_type(graph),
            "edge_types": self.edge_count_by_type(graph),
            "version": graph.version,
        }
