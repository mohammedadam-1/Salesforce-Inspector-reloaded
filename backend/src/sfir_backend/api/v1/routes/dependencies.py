from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_graph_service,
    get_rbac_service,
)
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.application.use_cases.rbac import RBACUseCase

router = APIRouter(prefix="/dependencies", tags=["Dependencies"])


@router.get("")
async def list_dependencies(
    component_type: str | None = Query(default=None),
    component_name: str | None = Query(default=None),
    depth: int = Query(default=1, ge=1, le=5),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    if component_type and component_name:
        result = await graph_service.get_node_dependencies(
            graph, component_type, component_name, depth,
        )
        return {"dependencies": result, "source": f"{component_type}/{component_name}"}
    return {"dependencies": [], "total": graph.edge_count}


@router.get("/{component_type}/{component_name}")
async def get_component_dependencies(
    component_type: str,
    component_name: str,
    depth: int = Query(default=1, ge=1, le=5),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    result = await graph_service.get_node_dependencies(
        graph, component_type, component_name, depth,
    )
    return result


@router.get("/{component_type}/{component_name}/tree")
async def get_dependency_tree(
    component_type: str,
    component_name: str,
    depth: int = Query(default=3, ge=1, le=10),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    result = await graph_service.get_node_dependencies(
        graph, component_type, component_name, depth,
    )
    return {"tree": result, "max_depth": depth}


@router.get("/{component_type}/{component_name}/reverse")
async def get_reverse_dependencies(
    component_type: str,
    component_name: str,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    impacted = await graph_service.find_impact(
        graph, component_type, component_name, 1,
    )
    return {"reverse_dependencies": impacted, "count": len(impacted)}


@router.get("/{component_type}/{component_name}/graph")
async def get_dependency_graph(
    component_type: str,
    component_name: str,
    depth: int = Query(default=2, ge=1, le=5),
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: GraphService = Depends(get_graph_service),
) -> dict[str, Any]:
    if not org_id:
        return {"error": "Organization context required"}
    graph = await graph_service.build_graph(org_id)
    deps = await graph_service.get_node_dependencies(
        graph, component_type, component_name, depth,
    )
    return {
        "nodes": graph.node_count,
        "edges": graph.edge_count,
        "dependencies": deps,
    }
