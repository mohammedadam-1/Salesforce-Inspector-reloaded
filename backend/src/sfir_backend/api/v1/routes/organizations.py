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
    UpdateOrganizationRequest,
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


@router.get("/organizations/{organization_id}")
async def get_organization(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> OrganizationResponse:
    result = await org_service.get_by_id(organization_id, user_id)
    if result is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Organization not found")
    return result


@router.put("/organizations/{organization_id}")
async def update_organization(
    organization_id: uuid.UUID,
    update: UpdateOrganizationRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> OrganizationResponse:
    return await org_service.update(organization_id, update, user_id)


@router.delete("/organizations/{organization_id}", status_code=204)
async def delete_organization(
    organization_id: uuid.UUID,
    user_id: uuid.UUID = Depends(get_current_user_id),
    org_service: OrganizationUseCase = Depends(get_org_service),
) -> None:
    await org_service.delete(organization_id, user_id)
