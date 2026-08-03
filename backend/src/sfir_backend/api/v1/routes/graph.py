from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from sfir_backend.api.deps import (
    get_current_org_id,
    get_graph_service,
    get_request_context,
)
from sfir_backend.application.use_cases.graph.repository_service import (
    RepositoryGraphService,
)
from sfir_backend.domain.request_context import RequestContext

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/build")
async def build_graph(
    metadata_types: list[str] | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, metadata_types, request_context)
    return {"node_count": graph.node_count, "edge_count": graph.edge_count}


@router.post("/incremental")
async def incremental_update(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    """Incremental rebuild placeholder: callers pass repo change sets via the
    service directly; this endpoint ensures the current org graph is present.
    """
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    return {"node_count": graph.node_count, "edge_count": graph.edge_count}


@router.get("/summary")
async def graph_summary(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    return await service.graph_summary(graph)


@router.get("/dependencies/{component_type}/{component_name}")
async def get_dependencies(
    component_type: str,
    component_name: str,
    depth: int = 1,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    return await service.get_node_dependencies(graph, component_type, component_name, depth)


@router.get("/impact/{component_type}/{component_name}")
async def find_impact(
    component_type: str,
    component_name: str,
    max_depth: int = 3,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    impacted = await service.find_impact(graph, component_type, component_name, max_depth)
    return {"impacted_components": impacted, "count": len(impacted)}


@router.get("/cycles")
async def find_cycles(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    cycles = await service.find_cycles(graph)
    return {"cycles": cycles, "count": len(cycles)}


@router.get("/nodes")
async def list_nodes(
    component_type: str | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, request_context=request_context)
    nodes = [
        {
            "component_type": n.node_type.value if n.node_type else "unknown",
            "component_name": n.api_name,
            "component_id": n.id,
        }
        for n in graph.nodes.values()
        if not component_type or (n.node_type and n.node_type.value == component_type)
    ]
    return {"nodes": nodes, "count": len(nodes)}


# ── Phase 4 ops ───────────────────────────────────────────────

@router.get("/node/{component_type}/{component_name}")
async def get_node(
    component_type: str,
    component_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    node = await service.get_node(f"{component_type}:{component_name}")
    if node is None:
        return {"node": None}
    return {
        "node": {
            "component_type": node.node_type.value if node.node_type else "unknown",
            "component_name": node.api_name,
            "component_id": node.id,
            "label": node.label,
            "namespace": node.namespace,
        }
    }


@router.get("/neighbors/{component_type}/{component_name}")
async def get_neighbors(
    component_type: str,
    component_name: str,
    depth: int = 1,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    neighbors = await service.get_neighbors(f"{component_type}:{component_name}", depth)
    return {
        "neighbors": [
            {
                "component_type": n.node_type.value if n.node_type else "unknown",
                "component_name": n.api_name,
                "component_id": n.id,
            }
            for n in neighbors
        ],
        "count": len(neighbors),
    }


@router.get("/where-used/{component_name}")
async def find_where_used(
    component_name: str,
    metadata_type: str | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    nodes = await service.find_where_used(component_name, metadata_type)
    return {
        "where_used": [
            {
                "component_type": n.node_type.value if n.node_type else "unknown",
                "component_name": n.api_name,
                "component_id": n.id,
            }
            for n in nodes
        ],
        "count": len(nodes),
    }


@router.get("/path/{source_type}/{source_name}/{target_type}/{target_name}")
async def find_path(
    source_type: str,
    source_name: str,
    target_type: str,
    target_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    path = await service.find_path(f"{source_type}:{source_name}", f"{target_type}:{target_name}")
    if path is None:
        return {"path": None, "found": False}
    return {"path": path, "found": True, "length": len(path)}


@router.get("/shortest-path/{source_type}/{source_name}/{target_type}/{target_name}")
async def shortest_path(
    source_type: str,
    source_name: str,
    target_type: str,
    target_name: str,
    max_depth: int = 10,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    result = await service.shortest_path(
        f"{source_type}:{source_name}", f"{target_type}:{target_name}",
    )
    paths = getattr(result, "paths", []) if result else []
    return {
        "paths": [getattr(p, "nodes", p) for p in paths],
        "count": len(paths),
    }


@router.get("/components")
async def connected_components(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    components = await service.connected_components()
    return {"components": components, "count": len(components)}


@router.get("/subgraph/{component_type}/{component_name}")
async def get_subgraph(
    component_type: str,
    component_name: str,
    depth: int = 1,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    sub = await service.get_subgraph(f"{component_type}:{component_name}", depth)
    return {
        "nodes": [
            {
                "component_type": n.node_type.value if n.node_type else "unknown",
                "component_name": n.api_name,
                "component_id": n.id,
            }
            for n in sub.nodes.values()
        ],
        "edges": [
            {
                "source_id": e.source_id,
                "target_id": e.target_id,
                "edge_type": e.edge_type.value if e.edge_type else "unknown",
            }
            for e in sub.edges.values()
        ],
        "node_count": sub.node_count,
        "edge_count": sub.edge_count,
    }


@router.get("/export")
async def export_graph(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext | None = Depends(get_request_context),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    await service.build_graph(org_id, request_context=request_context)
    return await service.export()
