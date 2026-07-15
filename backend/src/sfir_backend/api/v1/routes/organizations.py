import uuid

from fastapi import APIRouter, Depends, Request

from sfir_backend.api.deps import (
    get_current_user_id,
    get_org_service,
)
from sfir_backend.application.dto.organization import (
    CreateOrganizationRequest,
    OrganizationResponse,
    SwitchOrganizationResponse,
)
from sfir_backend.application.use_cases.organization import OrganizationUseCase

router = APIRouter(tags=["Organizations"])


@router.post("/organizations")
async def create_organization(
    request: CreateOrganizationRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> OrganizationResponse:
    return await org_service.create(request, user_id)


@router.get("/organizations")
async def list_organizations(
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> list[OrganizationResponse]:
    return await org_service.list_for_user(user_id)


@router.post("/organizations/{organization_id}/switch")
async def switch_organization(
    organization_id: uuid.UUID,
    http_request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> SwitchOrganizationResponse:
    ip_address = http_request.client.host if http_request.client else ""
    return await org_service.switch_organization(
        user_id, organization_id, ip_address,
    )


@router.get("/organizations/current")
async def get_current_organization(
    request: Request,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> OrganizationResponse | None:
    org_id: uuid.UUID | None = getattr(request.state, "org_id", None)
    return await org_service.get_current(user_id, org_id)
