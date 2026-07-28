from __future__ import annotations

from collections import deque

from sfir_backend.domain.graph.models import (
    Graph,
    GraphEdge,
    GraphNode,
)
from sfir_backend.domain.graph.traversal import (
    DependencyPath,
    TraversalContext,
    TraversalResult,
)


class GraphTraversalEngine:
    def dfs(
        self,
        graph: Graph,
        start_node_key: str,
        context: TraversalContext | None = None,
    ) -> TraversalResult:
        ctx = context or TraversalContext()
        result = TraversalResult()
        visited: set[str] = set()
        path_nodes: list[GraphNode] = []
        path_edges: list[GraphEdge] = []
        rec_stack: set[str] = set()

        def _dfs(current_key: str, depth: int) -> None:
            if depth > ctx.max_depth or len(visited) > ctx.max_nodes:
                result.truncated = True
                return
            if current_key in rec_stack and ctx.stop_on_cycle:
                cycle = list(rec_stack)
                result.cycles_detected.append(cycle)
                return
            if current_key in visited:
                return
            node = graph.get_node(current_key)
            if node is None:
                return
            visited.add(current_key)
            rec_stack.add(current_key)
            path_nodes.append(node)
            result.total_nodes_visited += 1

            if ctx.node_types and node.node_type not in ctx.node_types:
                rec_stack.discard(current_key)
                return

            edges = graph.get_outgoing_edges(current_key)
            for edge in edges:
                if ctx.edge_types and edge.edge_type.value not in ctx.edge_types:
                    continue
                path_edges.append(edge)
                result.total_edges_traversed += 1
                _dfs(edge.target_id, depth + 1)

            rec_stack.discard(current_key)

        _dfs(start_node_key, 0)
        for n in path_nodes:
            result.nodes[n.key] = n
        for e in path_edges:
            result.edges[e.id] = e
        if path_nodes:
            result.paths.append(
                DependencyPath(nodes=path_nodes, edges=path_edges, total_depth=len(path_edges)),
            )
        return result

    def bfs(
        self,
        graph: Graph,
        start_node_key: str,
        context: TraversalContext | None = None,
    ) -> TraversalResult:
        ctx = context or TraversalContext()
        result = TraversalResult()
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        queue.append((start_node_key, 0))
        path_nodes: list[GraphNode] = []
        path_edges: list[GraphEdge] = []

        while queue and len(visited) <= ctx.max_nodes:
            current_key, depth = queue.popleft()
            if depth > ctx.max_depth:
                result.truncated = True
                continue
            if current_key in visited:
                continue
            node = graph.get_node(current_key)
            if node is None:
                continue
            visited.add(current_key)
            path_nodes.append(node)
            result.total_nodes_visited += 1

            if ctx.node_types and node.node_type not in ctx.node_types:
                continue

            edges = graph.get_outgoing_edges(current_key)
            for edge in edges:
                if ctx.edge_types and edge.edge_type.value not in ctx.edge_types:
                    continue
                path_edges.append(edge)
                result.total_edges_traversed += 1
                if edge.target_id not in visited:
                    queue.append((edge.target_id, depth + 1))

        for n in path_nodes:
            result.nodes[n.key] = n
        for e in path_edges:
            result.edges[e.id] = e
        if path_nodes:
            result.paths.append(
                DependencyPath(nodes=path_nodes, edges=path_edges, total_depth=len(path_edges)),
            )
        return result

    def shortest_path(
        self,
        graph: Graph,
        from_node_key: str,
        to_node_key: str,
        context: TraversalContext | None = None,
    ) -> TraversalResult:
        ctx = context or TraversalContext()
        result = TraversalResult()

        if from_node_key not in graph.nodes or to_node_key not in graph.nodes:
            return result

        visited: set[str] = set()
        queue: deque[list[str]] = deque()
        queue.append([from_node_key])
        found_path: list[str] | None = None

        while queue and len(visited) <= ctx.max_nodes:
            path = queue.popleft()
            current_key = path[-1]
            if len(path) - 1 > ctx.max_depth:
                result.truncated = True
                continue
            if current_key in visited:
                continue
            visited.add(current_key)

            if current_key == to_node_key:
                found_path = path
                break

            edges = graph.get_outgoing_edges(current_key)
            for edge in edges:
                if edge.target_id not in visited:
                    new_path = [*path, edge.target_id]
                    queue.append(new_path)

        if found_path:
            path_nodes: list[GraphNode] = []
            path_edges: list[GraphEdge] = []
            for i, node_key in enumerate(found_path):
                node = graph.get_node(node_key)
                if node:
                    path_nodes.append(node)
                    result.nodes[node.key] = node
                    result.total_nodes_visited += 1
                if i < len(found_path) - 1:
                    edges_out = graph.get_outgoing_edges(node_key)
                    for e in edges_out:
                        if e.target_id == found_path[i + 1]:
                            path_edges.append(e)
                            result.edges[e.id] = e
                            result.total_edges_traversed += 1
                            break
            result.paths.append(
                DependencyPath(nodes=path_nodes, edges=path_edges, total_depth=len(path_edges)),
            )

        return result

    def find_descendants(
        self,
        graph: Graph,
        node_key: str,
        depth: int = 5,
    ) -> list[GraphNode]:
        ctx = TraversalContext(max_depth=depth)
        result = self.dfs(graph, node_key, ctx)
        descendants: list[GraphNode] = []
        for n in result.nodes.values():
            if n.key != node_key:
                descendants.append(n)
        return descendants

    def find_ancestors(
        self,
        graph: Graph,
        node_key: str,
        depth: int = 5,
    ) -> list[GraphNode]:
        result = TraversalResult()
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()
        queue.append((node_key, 0))

        while queue:
            current_key, d = queue.popleft()
            if d >= depth or current_key in visited:
                continue
            visited.add(current_key)
            edges = graph.get_incoming_edges(current_key)
            for edge in edges:
                if edge.source_id not in visited:
                    node = graph.get_node(edge.source_id)
                    if node:
                        result.nodes[node.key] = node
                        result.total_nodes_visited += 1
                    queue.append((edge.source_id, d + 1))

        ancestors: list[GraphNode] = []
        for n in result.nodes.values():
            if n.key != node_key:
                ancestors.append(n)
        return ancestors

    def subgraph(
        self,
        graph: Graph,
        node_keys: set[str],
        depth: int = 1,
    ) -> Graph:
        sub = Graph(version=graph.version, created_at=graph.created_at)
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque()

        for key in node_keys:
            queue.append((key, 0))
            node = graph.get_node(key)
            if node:
                sub.add_node(node)

        while queue:
            current_key, d = queue.popleft()
            if current_key in visited or d >= depth:
                continue
            visited.add(current_key)
            for edge in graph.get_outgoing_edges(current_key):
                sub.nodes.setdefault(edge.source_id, graph.get_node(edge.source_id))
                sub.nodes.setdefault(edge.target_id, graph.get_node(edge.target_id))
                sub.add_edge(edge)
                queue.append((edge.target_id, d + 1))

        return sub
