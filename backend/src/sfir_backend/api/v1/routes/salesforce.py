import uuid

from fastapi import APIRouter, Depends, Request

from sfir_backend.api.deps import get_current_org_id, get_current_user_id, get_salesforce_service
from sfir_backend.application.dto.salesforce import (
    SalesforceCallbackRequest,
    SalesforceConnectionResponse,
    SalesforceConnectRequest,
    SalesforceConnectResponse,
    SalesforceHealthResponse,
)
from sfir_backend.application.use_cases.salesforce import SalesforceUseCase

router = APIRouter(prefix="/salesforce", tags=["Salesforce"])


@router.post("/connect")
async def initiate_connect(
    request: SalesforceConnectRequest,
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
    sf_service: SalesforceUseCase = Depends(get_salesforce_service),
) -> SalesforceConnectResponse:
    return await sf_service.initiate_connect(request, org_id, user_id)


@router.get("/callback")
async def oauth_callback(
    code: str,
    state: str,
    environment: str = "production",
    http_request: Request = None,
    sf_service: SalesforceUseCase = Depends(get_salesforce_service),
) -> SalesforceConnectionResponse:
    ip_address = http_request.client.host if http_request and http_request.client else ""
    callback_request = SalesforceCallbackRequest(
        code=code,
        state=state,
        code_verifier="",
        environment=environment,
    )
    # Identity (user/org) and PKCE verifier are resolved server-side from the
    # single-use OAuthSession; the placeholder ids below are ignored by the
    # use case (browser redirect carries no JWT).
    return await sf_service.handle_callback(
        callback_request,
        organization_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        ip_address=ip_address,
    )


@router.post("/disconnect")
async def disconnect(
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
    http_request: Request = None,
    sf_service: SalesforceUseCase = Depends(get_salesforce_service),
) -> dict[str, str]:
    ip_address = http_request.client.host if http_request and http_request.client else ""
    await sf_service.disconnect(org_id, user_id, ip_address)
    return {"message": "Salesforce connection disconnected"}


@router.get("/status")
async def get_status(
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
    sf_service: SalesforceUseCase = Depends(get_salesforce_service),
) -> SalesforceConnectionResponse | None:
    return await sf_service.get_status(org_id, user_id)


@router.get("/health")
async def check_health(
    org_id: str = Depends(get_current_org_id),
    user_id: str = Depends(get_current_user_id),
    sf_service: SalesforceUseCase = Depends(get_salesforce_service),
) -> SalesforceHealthResponse:
    return await sf_service.check_health(org_id, user_id)
