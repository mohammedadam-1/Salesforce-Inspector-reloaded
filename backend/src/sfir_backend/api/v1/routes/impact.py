from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_graph_service,
    get_request_context,
    get_rbac_service,
)
from sfir_backend.api.dto.impact import (
    ImpactAnalysisRequest,
    ImpactAnalysisResponse,
    ImpactedComponent,
    ImpactReport,
    ImpactSimulateRequest,
)
from sfir_backend.application.use_cases.graph.repository_service import (
    RepositoryGraphService,
)
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.domain.request_context import RequestContext

router = APIRouter(prefix="/impact-analysis", tags=["Impact Analysis"])


@router.post("")
async def run_impact_analysis(
    request: ImpactAnalysisRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext = Depends(get_request_context),
) -> ImpactAnalysisResponse:
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Organization context required")
    await rbac.require_permission(_user_id, org_id, "impact:analyze")
    graph = await graph_service.build_graph(org_id, request_context=request_context)
    impacted = await graph_service.find_impact(
        graph, request.component_type, request.component_name, request.max_depth,
    )
    return ImpactAnalysisResponse(
        id=uuid.uuid4(),
        source_type=request.component_type,
        source_name=request.component_name,
        impacted_components=[
            ImpactedComponent(
                component_type=c.get("component_type", ""),
                component_name=c.get("component_name", ""),
                component_id=c.get("component_id", ""),
                impact_depth=c.get("depth", 1),
            )
            for c in impacted
        ],
        total_impacted=len(impacted),
        max_depth=request.max_depth,
        created_at=datetime.now(UTC),
    )


@router.post("/simulate")
async def simulate_impact(
    request: ImpactSimulateRequest,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
    graph_service: RepositoryGraphService = Depends(get_graph_service),
    request_context: RequestContext = Depends(get_request_context),
) -> ImpactAnalysisResponse:
    if not org_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Organization context required")
    graph = await graph_service.build_graph(org_id, request_context=request_context)
    impacted = await graph_service.find_impact(
        graph, request.component_type, request.component_name, request.max_depth,
    )
    return ImpactAnalysisResponse(
        id=uuid.uuid4(),
        source_type=request.component_type,
        source_name=request.component_name,
        impacted_components=[
            ImpactedComponent(
                component_type=c.get("component_type", ""),
                component_name=c.get("component_name", ""),
                component_id=c.get("component_id", ""),
                impact_depth=c.get("depth", 1),
                change_type=request.change_type,
            )
            for c in impacted
        ],
        total_impacted=len(impacted),
        max_depth=request.max_depth,
        created_at=datetime.now(UTC),
    )


@router.get("/{analysis_id}")
async def _get_impact_analysis(
    analysis_id: uuid.UUID,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> ImpactAnalysisResponse | None:
    return None


@router.get("/{analysis_id}/report")
async def _get_impact_report(
    analysis_id: uuid.UUID,
    org_id: uuid.UUID | None = Depends(get_current_org_id),
    _user_id: uuid.UUID = Depends(get_current_user_id),
    _rbac: RBACUseCase = Depends(get_rbac_service),
) -> ImpactReport | None:
    return None
