"""SFIR Backend — FastAPI Application Factory.

This module bootstraps the entire application following hexagonal architecture.
The application is configured via the DI container, middleware, and routes.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import generate_latest
from starlette.responses import PlainTextResponse

from sfir_backend.api.errors import add_error_handlers
from sfir_backend.api.middleware import add_middleware
from sfir_backend.api.security_middleware import add_security_middleware
from sfir_backend.api.v1.routes import api_router
from sfir_backend.api.websocket import authenticate_websocket, get_ws_manager
from sfir_backend.config.container import Container
from sfir_backend.config.settings import Settings, get_settings
from sfir_backend.infrastructure.observability.logging import (
    configure_logging,
)
from sfir_backend.infrastructure.observability.tracing import (
    configure_tracing,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan — startup and shutdown."""
    settings = get_settings()

    configure_logging(
        log_format=settings.log_format,
    )

    configure_tracing(settings)

    container = Container(settings)
    await container.startup()
    app.state.container = container

    logger.info(
        "application_started",
        environment=settings.environment,
        log_level=settings.log_level,
        tracing_enabled=settings.tracing_enabled,
    )

    yield

    await container.shutdown()
    logger.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="SFIR Backend API",
        description=(
            "Production backend for the Salesforce Inspector Reloaded "
            "platform. Provides metadata synchronization, dependency "
            "analysis, impact analysis, AI-powered documentation, "
            "and search for Salesforce organizations."
        ),
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # Security middleware
    # Rate limit middleware added in lifespan after container is ready
    add_security_middleware(app, settings)

    # Middleware (logging, metrics, tracing)
    add_middleware(app)

    # CORS (outermost — must handle preflight before any other middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error handlers
    add_error_handlers(app)

    # Routes
    app.include_router(api_router)

    # Version endpoint
    @app.get("/version")
    async def version() -> dict:
        return {
            "service": "sfir-backend",
            "version": "0.1.0",
            "environment": settings.environment,
        }

    # WebSocket endpoint
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        container: Container = app.state.container
        user_id = await authenticate_websocket(websocket, container)
        if not user_id:
            await websocket.close(code=4001)
            return
        ws_manager = get_ws_manager()
        await ws_manager.handle_connection(websocket, user_id)

    # Prometheus metrics
    if settings.metrics_enabled:

        @app.get("/metrics")
        async def metrics() -> PlainTextResponse:
            return PlainTextResponse(
                content=generate_latest().decode("utf-8"),
                media_type="text/plain; version=0.0.4",
            )

    return app


app = create_app()
