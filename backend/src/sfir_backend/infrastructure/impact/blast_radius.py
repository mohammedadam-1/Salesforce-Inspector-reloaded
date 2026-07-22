from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from sfir_backend.domain.graph.models import Graph
from sfir_backend.domain.impact.models import BlastRadius


@dataclass
class _BFSResult:
    keys: set[str]
    depth_map: dict[str, int]
    type_counts: dict[str, int]


class BlastRadiusCalculator:
    def calculate(
        self,
        graph: Graph,
        component_key: str,
        max_depth: int = 5,
    ) -> BlastRadius:
        if component_key not in graph.nodes:
            return BlastRadius(
                total_count=0,
                direct_count=0,
                by_type={},
                max_depth=0,
                has_circular_dependency=False,
            )

        bfs = self._bfs(graph, component_key, max_depth)

        if component_key in bfs.keys:
            bfs.keys.discard(component_key)

        direct = {
            k for k in bfs.keys
            if bfs.depth_map.get(k, 99) == 1
        }

        circular = self._detect_cycles_in_subgraph(graph, bfs.keys)

        return BlastRadius(
            total_count=len(bfs.keys),
            direct_count=len(direct),
            by_type=dict(sorted(bfs.type_counts.items())),
            max_depth=max(bfs.depth_map.values()) if bfs.depth_map else 0,
            has_circular_dependency=circular,
        )

    def _bfs(self, graph: Graph, start: str, max_depth: int) -> _BFSResult:
        visited: set[str] = set()
        depth_map: dict[str, int] = {}
        type_counts: dict[str, int] = defaultdict(int)
        queue: deque[tuple[str, int]] = deque()
        queue.append((start, 0))
        visited.add(start)

        while queue:
            current, depth = queue.popleft()
            if depth >= max_depth:
                continue

            for edge in graph.get_outgoing_edges(current):
                neighbor = edge.target_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    depth_map[neighbor] = depth + 1
                    node = graph.get_node(neighbor)
                    if node and node.node_type:
                        type_counts[node.node_type.value] += 1
                    queue.append((neighbor, depth + 1))

            for edge in graph.get_incoming_edges(current):
                neighbor = edge.source_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    depth_map[neighbor] = depth + 1
                    node = graph.get_node(neighbor)
                    if node and node.node_type:
                        type_counts[node.node_type.value] += 1
                    queue.append((neighbor, depth + 1))

        return _BFSResult(keys=visited, depth_map=depth_map, type_counts=type_counts)

    def _detect_cycles_in_subgraph(self, graph: Graph, nodes: set[str]) -> bool:
        visited: set[str] = set()
        rec_stack: set[str] = set()

        def dfs(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for edge in graph.get_outgoing_edges(node):
                neighbor = edge.target_id
                if neighbor not in nodes:
                    continue
                if neighbor not in visited:
                    if dfs(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.discard(node)
            return False

        return any(n not in visited and dfs(n) for n in nodes)
