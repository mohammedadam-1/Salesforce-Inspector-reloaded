import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.api.middleware import _build_authenticated_context
from sfir_backend.application.use_cases.ai.agent import AgentService
from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.application.use_cases.auth import AuthUseCase
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.application.use_cases.organization import OrganizationUseCase
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.application.use_cases.salesforce import SalesforceUseCase
from sfir_backend.config.container import Container
from sfir_backend.domain.request_context import RequestContext
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine
from sfir_backend.infrastructure.jobs.engine import JobEngine
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.application import (
    AuthenticationFailedError,
)
from sfir_backend.shared.middleware.tenant_context import set_request_context


async def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(
    container: Container = Depends(get_container),
) -> AsyncIterator[AsyncSession]:
    session = container.create_session()
    try:
        yield session
    finally:
        await session.close()


async def get_jwt_service(
    container: Container = Depends(get_container),
) -> JWTService:
    return container.get_service("jwt")


async def get_optional_request_context(
    request: Request,
    authorization: str | None = Header(default=None),
    container: Container = Depends(get_container),
) -> RequestContext:
    context = getattr(request.state, "request_context", None)
    if isinstance(context, RequestContext):
        if getattr(request.state, "auth_error", None):
            raise AuthenticationFailedError("Invalid or expired token")
        return context

    if not authorization:
        context = RequestContext.anonymous(
            request_id=request.headers.get("x-request-id"),
            trace_id=request.headers.get("x-trace-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            request_source=request.headers.get("x-request-source"),
            client_version=request.headers.get("x-client-version"),
            extension_version=request.headers.get("x-extension-version"),
        )
        request.state.request_context = context
        set_request_context(context)
        return context

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationFailedError("Invalid authorization scheme")

    jwt_service: JWTService = container.get_service("jwt")
    try:
        payload = jwt_service.decode_access_token(token)
        user_id = uuid.UUID(payload["sub"])
        org_id = uuid.UUID(payload["org"]) if payload.get("org") else None
    except (ValueError, KeyError):
        raise AuthenticationFailedError("Invalid or expired token") from None

    context = await _build_authenticated_context(
        request=request,
        payload=payload,
        user_id=user_id,
        org_id=org_id,
    )
    request.state.jwt_payload = payload
    request.state.user_id = user_id
    request.state.org_id = org_id
    request.state.request_context = context
    set_request_context(context)
    return context


async def get_request_context(
    context: RequestContext = Depends(get_optional_request_context),
) -> RequestContext:
    return context.require_authenticated()


async def get_current_user_id(
    context: RequestContext = Depends(get_request_context),
) -> uuid.UUID:
    if context.user_id is None:
        raise AuthenticationFailedError("Missing authorization header")
    return context.user_id


async def get_current_org_id(
    context: RequestContext = Depends(get_request_context),
) -> uuid.UUID | None:
    return context.organization_id


async def get_auth_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> AuthUseCase:
    return container.create_auth_use_case(db)


async def get_org_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> OrganizationUseCase:
    return container.create_org_use_case(db)


async def get_rbac_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> RBACUseCase:
    return container.create_rbac_use_case(db)


async def get_salesforce_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> SalesforceUseCase:
    return container.create_salesforce_use_case(db)


async def get_sync_coordinator(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> SyncCoordinator:
    return container.create_sync_coordinator(db)


async def get_graph_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> GraphService:
    return container.create_graph_service(db)


async def get_agent_service(
    container: Container = Depends(get_container),
    db: AsyncSession = Depends(get_db),
) -> AgentService:
    return container.create_agent_service(db)


async def get_ai_orchestrator(
    container: Container = Depends(get_container),
) -> AIOrchestrator:
    return container.get_use_case("ai_orchestrator")


async def get_conversation_manager(
    container: Container = Depends(get_container),
) -> ConversationManager:
    orchestrator: AIOrchestrator = container.get_use_case("ai_orchestrator")
    return orchestrator.conversation_manager


async def get_documentation_engine(
    container: Container = Depends(get_container),
) -> DocumentationEngine:
    return container.get_service("documentation_engine")

async def get_job_engine(
    container: Container = Depends(get_container),
) -> JobEngine:
    return container.get_service("job_engine")
