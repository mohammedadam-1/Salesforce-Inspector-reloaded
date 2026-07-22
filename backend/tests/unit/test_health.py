"""Tests for health endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from sfir_backend.config.settings import Settings
from sfir_backend.main import create_app


@pytest.mark.asyncio
async def test_health_live() -> None:
    """Liveness endpoint should return 200."""
    settings = Settings(environment="testing")
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/live")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_ready_without_container() -> None:
    """Readiness should not fail when container is not fully initialized.

    When the app is created in testing mode without a database,
    the readiness check should return a non-error response.
    """
    settings = Settings(environment="testing")
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/ready")
        assert response.status_code in (200, 503)


@pytest.mark.asyncio
async def test_health_status() -> None:
    """Status endpoint should return version info."""
    settings = Settings(environment="testing")
    app = create_app(settings)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health/status")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "sfir-backend"
        assert data["version"] == "0.1.0"
