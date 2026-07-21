import uuid
from collections.abc import AsyncIterator

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sfir_backend.application.use_cases.ai.agent import AgentService
from sfir_backend.application.use_cases.ai.conversation_manager import (
    ConversationManager,
)
from sfir_backend.application.use_cases.ai.orchestrator import AIOrchestrator
from sfir_backend.application.use_cases.auth import AuthUseCase
from sfir_backend.application.use_cases.graph.service import GraphService
from sfir_backend.application.use_cases.metadata_sync import SyncCoordinator
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine
from sfir_backend.application.use_cases.organization import OrganizationUseCase
from sfir_backend.application.use_cases.rbac import RBACUseCase
from sfir_backend.application.use_cases.salesforce import SalesforceUseCase
from sfir_backend.config.container import Container
from sfir_backend.infrastructure.jobs.engine import JobEngine
from sfir_backend.infrastructure.security.jwt import JWTService
from sfir_backend.shared.exceptions.application import (
    AuthenticationFailedError,
)
from sfir_backend.shared.middleware.tenant_context import current_org_id


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


async def get_current_user_id(
    authorization: str | None = Header(default=None),
    container: Container = Depends(get_container),
) -> uuid.UUID:
    if not authorization:
        raise AuthenticationFailedError("Missing authorization header")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise AuthenticationFailedError("Invalid authorization scheme")

    jwt_service: JWTService = container.get_service("jwt")
    try:
        payload = jwt_service.decode_access_token(token)
        return uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        raise AuthenticationFailedError("Invalid or expired token") from None


async def get_current_org_id() -> uuid.UUID | None:
    return current_org_id.get()


async def get_auth_service(
    container: Container = Depends(get_container),
) -> AuthUseCase:
    return container.get_use_case("auth")


async def get_org_service(
    container: Container = Depends(get_container),
) -> OrganizationUseCase:
    return container.get_use_case("organization")


async def get_rbac_service(
    container: Container = Depends(get_container),
) -> RBACUseCase:
    return container.get_use_case("rbac")


async def get_salesforce_service(
    container: Container = Depends(get_container),
) -> SalesforceUseCase:
    return container.get_use_case("salesforce")


async def get_sync_coordinator(
    container: Container = Depends(get_container),
) -> SyncCoordinator:
    return container.get_use_case("sync_coordinator")


async def get_graph_service(
    container: Container = Depends(get_container),
) -> GraphService:
    return container.get_use_case("graph_service")


async def get_agent_service(
    container: Container = Depends(get_container),
) -> AgentService:
    return container.get_use_case("agent_service")


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
