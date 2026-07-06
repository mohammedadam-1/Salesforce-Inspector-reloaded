"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.cache.redis import close_redis, init_redis
from sfir_backend.infrastructure.database.session import engine
from sfir_backend.infrastructure.observability.logging import configure_logging
from sfir_backend.infrastructure.observability.metrics import MetricsMiddleware
from sfir_backend.infrastructure.observability.tracing import configure_tracing

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    if settings.tracing_enabled:
        configure_tracing(settings)
    await init_redis(settings)
    logger.info("application_started", environment=settings.environment)
    yield
    await close_redis()
    await engine.dispose()
    logger.info("application_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SFIR Backend API",
        description="AI-powered Salesforce Inspector platform backend",
        version="0.1.0",
        docs_url="/api/docs" if settings.is_development else None,
        redoc_url="/api/redoc" if settings.is_development else None,
        openapi_url="/api/openapi.json" if settings.is_development else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(MetricsMiddleware)

    from sfir_backend.api.v1.routes.health import router as health_router
    from sfir_backend.api.v1.routes.auth import router as auth_router
    from sfir_backend.api.v1.routes.organizations import router as org_router
    from sfir_backend.api.v1.routes.users import router as users_router
    from sfir_backend.api.v1.routes.roles import router as roles_router
    from sfir_backend.api.v1.routes.api_keys import router as api_keys_router
    from sfir_backend.api.v1.routes.connections import router as connections_router
    from sfir_backend.api.v1.routes.metadata import router as metadata_router
    from sfir_backend.api.v1.routes.dependencies import router as dependencies_router
    from sfir_backend.api.v1.routes.ai import router as ai_router

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(org_router, prefix="/api/v1")
    app.include_router(users_router, prefix="/api/v1")
    app.include_router(roles_router, prefix="/api/v1")
    app.include_router(api_keys_router, prefix="/api/v1")
    app.include_router(connections_router, prefix="/api/v1")
    app.include_router(metadata_router, prefix="/api/v1")
    app.include_router(dependencies_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")

    return app
