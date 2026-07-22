from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends

from sfir_backend.api.deps import get_current_org_id, get_graph_service
from sfir_backend.application.use_cases.graph.service import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


@router.post("/build")
async def build_graph(
    metadata_types: list[str] | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id, metadata_types)
    return {"node_count": graph.node_count, "edge_count": graph.edge_count}


@router.get("/summary")
async def graph_summary(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id)
    return await service.graph_summary(graph)


@router.get("/dependencies/{component_type}/{component_name}")
async def get_dependencies(
    component_type: str,
    component_name: str,
    depth: int = 1,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id)
    return await service.get_node_dependencies(graph, component_type, component_name, depth)


@router.get("/impact/{component_type}/{component_name}")
async def find_impact(
    component_type: str,
    component_name: str,
    max_depth: int = 3,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id)
    impacted = await service.find_impact(graph, component_type, component_name, max_depth)
    return {"impacted_components": impacted, "count": len(impacted)}


@router.get("/cycles")
async def find_cycles(
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id)
    cycles = await service.find_cycles(graph)
    return {"cycles": cycles, "count": len(cycles)}


@router.get("/nodes")
async def list_nodes(
    component_type: str | None = None,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await service.build_graph(org_id)
    nodes = [
        {
            "component_type": n.component_type,
            "component_name": n.component_name,
            "component_id": n.component_id,
        }
        for n in graph.nodes.values()
        if not component_type or n.component_type == component_type
    ]
    return {"nodes": nodes, "count": len(nodes)}
