"""Tests for the metadata sync API routes (dispatch behavior)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_sync_coordinator,
)
from sfir_backend.api.v1.routes import api_router
from sfir_backend.application.dto.metadata_sync import SyncJobResponse


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def connection_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def coordinator() -> AsyncMock:
    return AsyncMock()


def _job_response(org_id: uuid.UUID) -> SyncJobResponse:
    return SyncJobResponse(
        id=uuid.uuid4(),
        organization_id=org_id,
        connection_id=uuid.uuid4(),
        sync_type="full",
        status="queued",
        metadata_type=None,
        progress=0.0,
        total_items=0,
        processed_items=0,
        failed_items=0,
        error_message="",
        started_at=None,
        completed_at=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest.fixture
def app(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    coordinator: AsyncMock,
) -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)

    async def override_org_id() -> uuid.UUID:
        return org_id

    async def override_user_id() -> uuid.UUID:
        return user_id

    async def override_coordinator() -> AsyncMock:
        return coordinator

    application.dependency_overrides[get_current_org_id] = override_org_id
    application.dependency_overrides[get_current_user_id] = override_user_id
    application.dependency_overrides[get_sync_coordinator] = override_coordinator
    return application


@pytest.mark.asyncio
async def test_start_full_sync_dispatches_full_task(
    app: FastAPI,
    coordinator: AsyncMock,
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> None:
    coordinator.start_sync.return_value = _job_response(org_id)

    with patch(
        "sfir_backend.api.v1.routes.metadata_sync.full_sync_task",
        autospec=True,
    ) as full_task, patch(
        "sfir_backend.api.v1.routes.metadata_sync.incremental_sync_task",
        autospec=True,
    ) as incremental_task:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/sync/start", json={
                "connection_id": str(connection_id),
                "sync_type": "full",
            })

        assert response.status_code == 200
        coordinator.start_sync.assert_awaited_once()
        full_task.apply_async.assert_called_once_with(
            args=[str(org_id), str(connection_id)],
            queue="metadata",
        )
        incremental_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_start_incremental_sync_dispatches_incremental_task(
    app: FastAPI,
    coordinator: AsyncMock,
    org_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> None:
    coordinator.start_sync.return_value = _job_response(org_id)

    with patch(
        "sfir_backend.api.v1.routes.metadata_sync.full_sync_task",
        autospec=True,
    ) as full_task, patch(
        "sfir_backend.api.v1.routes.metadata_sync.incremental_sync_task",
        autospec=True,
    ) as incremental_task:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test",
        ) as client:
            response = await client.post("/api/v1/sync/start", json={
                "connection_id": str(connection_id),
                "sync_type": "incremental",
            })

        assert response.status_code == 200
        incremental_task.apply_async.assert_called_once_with(
            args=[str(org_id), str(connection_id)],
            queue="metadata",
        )
        full_task.apply_async.assert_not_called()
