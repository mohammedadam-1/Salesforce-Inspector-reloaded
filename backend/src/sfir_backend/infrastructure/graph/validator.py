from __future__ import annotations

from typing import Any

from sfir_backend.domain.graph.models import Graph


class GraphValidator:
    def validate(self, graph: Graph) -> dict[str, list[str]]:
        issues: dict[str, list[str]] = {
            "missing_nodes": [],
            "broken_edges": [],
            "duplicate_edges": [],
            "invalid_nodes": [],
        }

        seen_edge_keys: set[str] = set()
        for edge in graph.edges.values():
            if edge.source_id not in graph.nodes:
                issues["broken_edges"].append(
                    f"Edge {edge.id}: source {edge.source_id} not found",
                )
            if edge.target_id not in graph.nodes:
                issues["broken_edges"].append(
                    f"Edge {edge.id}: target {edge.target_id} not found",
                )
            edge_key = f"{edge.source_id}->{edge.target_id}:{edge.edge_type}"
            if edge_key in seen_edge_keys:
                issues["duplicate_edges"].append(f"Duplicate edge: {edge.id}")
            else:
                seen_edge_keys.add(edge_key)

        for node_key, node in graph.nodes.items():
            expected_key = f"{node.node_type.value}:{node.api_name}"
            if node_key != expected_key:
                issues["invalid_nodes"].append(
                    f"Node {node_key}: key mismatch, expected {expected_key}",
                )

        for node_key in graph.nodes:
            if node_key not in graph.outgoing:
                issues["invalid_nodes"].append(
                    f"Node {node_key}: missing outgoing adjacency entry",
                )
            if node_key not in graph.incoming:
                issues["invalid_nodes"].append(
                    f"Node {node_key}: missing incoming adjacency entry",
                )

        for edge_id in graph.outgoing.get("", []):
            if edge_id not in graph.edges:
                issues["broken_edges"].append(f"Orphaned edge reference: {edge_id}")

        return issues

    def integrity_check(self, graph: Graph) -> dict[str, Any]:
        issues = self.validate(graph)
        total_issues = sum(len(v) for v in issues.values())
        return {
            "is_valid": total_issues == 0,
            "node_count": graph.node_count,
            "edge_count": graph.edge_count,
            "outgoing_count": len(graph.outgoing),
            "incoming_count": len(graph.incoming),
            "total_issues": total_issues,
            "issues": issues,
        }

    def consistency_check(self, graph: Graph) -> dict[str, Any]:
        adjacency_mismatches: list[str] = []
        for node_key in graph.nodes:
            expected_outgoing = len(graph.get_outgoing_edges(node_key))
            actual_outgoing = len(graph.outgoing.get(node_key, []))
            if expected_outgoing != actual_outgoing:
                adjacency_mismatches.append(
                    f"Node {node_key}: outgoing count {expected_outgoing} vs {actual_outgoing}",
                )

        return {
            "consistent": len(adjacency_mismatches) == 0,
            "adjacency_mismatches": adjacency_mismatches,
        }
