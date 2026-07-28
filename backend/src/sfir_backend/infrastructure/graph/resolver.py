from __future__ import annotations

from sfir_backend.domain.graph.models import Graph, GraphNode, NodeType
from sfir_backend.domain.graph.traversal import DependencyPath
from sfir_backend.infrastructure.graph.traversal import GraphTraversalEngine


class DependencyResolver:
    def __init__(self, traversal: GraphTraversalEngine | None = None) -> None:
        self._traversal = traversal or GraphTraversalEngine()

    def where_used(
        self,
        graph: Graph,
        api_name: str,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        node_type = NodeType.OBJECT
        if metadata_type:
            type_map = {nt.value: nt for nt in NodeType}
            node_type = type_map.get(metadata_type, NodeType.OBJECT)
        node_key = f"{node_type.value}:{api_name}"
        ancestors = self._traversal.find_ancestors(graph, node_key)
        return ancestors

    def what_depends_on(
        self,
        graph: Graph,
        api_name: str,
        metadata_type: str | None = None,
    ) -> list[GraphNode]:
        node_type = NodeType.OBJECT
        if metadata_type:
            type_map = {nt.value: nt for nt in NodeType}
            node_type = type_map.get(metadata_type, NodeType.OBJECT)
        node_key = f"{node_type.value}:{api_name}"
        descendants = self._traversal.find_descendants(graph, node_key)
        return descendants

    def dependency_tree(
        self,
        graph: Graph,
        node_key: str,
        max_depth: int = 10,
    ) -> list[DependencyPath]:
        ctx = type("ctx", (), {"max_depth": max_depth, "max_nodes": 1000, "stop_on_cycle": True})()
        result = self._traversal.dfs(graph, node_key, ctx)
        return result.paths

    def reverse_dependency_tree(
        self,
        graph: Graph,
        node_key: str,
        max_depth: int = 10,
    ) -> list[DependencyPath]:
        ancestors = self._traversal.find_ancestors(graph, node_key, depth=max_depth)
        paths: list[DependencyPath] = []
        if ancestors:
            path_nodes = ancestors
            path_edges = []
            for _i, ancestor in enumerate(ancestors):
                edges = graph.get_incoming_edges(ancestor.key)
                path_edges.extend(edges)
            paths.append(
                DependencyPath(nodes=path_nodes, edges=path_edges, total_depth=len(path_edges)),
            )
        return paths

    def find_orphaned(self, graph: Graph) -> list[GraphNode]:
        orphaned: list[GraphNode] = []
        for node in graph.nodes.values():
            has_outgoing = bool(graph.get_outgoing_edges(node.key))
            has_incoming = bool(graph.get_incoming_edges(node.key))
            if not has_outgoing and not has_incoming:
                orphaned.append(node)
        return orphaned

    def find_unreachable(self, graph: Graph) -> list[GraphNode]:
        all_keys = set(graph.nodes.keys())
        reachable: set[str] = set()

        for node_key in list(graph.nodes.keys()):
            if node_key in reachable:
                continue
            outgoing = graph.get_outgoing_edges(node_key)
            incoming = graph.get_incoming_edges(node_key)
            if outgoing or incoming:
                reachable.add(node_key)
                for edge in outgoing:
                    reachable.add(edge.target_id)
                for edge in incoming:
                    reachable.add(edge.source_id)

        unreachable_keys = all_keys - reachable
        return [graph.nodes[k] for k in unreachable_keys if k in graph.nodes]

    def dependency_depth(
        self,
        graph: Graph,
        node_key: str,
    ) -> int:
        result = self._traversal.dfs(graph, node_key)
        if not result.paths:
            return 0
        return result.paths[0].total_depth
