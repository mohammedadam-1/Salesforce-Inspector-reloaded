from __future__ import annotations

from sfir_backend.domain.graph.models import Graph


class CycleDetectionEngine:
    def detect_cycles(self, graph: Graph) -> list[list[str]]:
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node_key: str, path: list[str]) -> None:
            visited.add(node_key)
            rec_stack.add(node_key)
            path.append(node_key)

            edges = graph.get_outgoing_edges(node_key)
            for edge in edges:
                if edge.target_id not in visited:
                    dfs(edge.target_id, path)
                elif edge.target_id in rec_stack:
                    idx = path.index(edge.target_id)
                    cycle = path[idx:]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node_key)

        for node_key in list(graph.nodes.keys()):
            if node_key not in visited:
                dfs(node_key, [])

        return cycles

    def has_cycles(self, graph: Graph) -> bool:
        cycles = self.detect_cycles(graph)
        return len(cycles) > 0

    def find_self_references(self, graph: Graph) -> list[str]:
        self_refs: list[str] = []
        for edge in graph.edges.values():
            if edge.source_id == edge.target_id:
                self_refs.append(edge.id)
        return self_refs

    def cycle_diagnostics(self, graph: Graph) -> dict[str, list[list[str]]]:
        cycles = self.detect_cycles(graph)
        self_refs = self.find_self_references(graph)
        return {
            "cycles": cycles,
            "self_references": self_refs,
            "cycle_count": len(cycles),
            "self_ref_count": len(self_refs),
        }
