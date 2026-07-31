"""Tests for the Documentation API routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport

from sfir_backend.api.deps import (
    get_current_org_id,
    get_current_user_id,
    get_documentation_engine,
    get_graph_service,
    get_rbac_service,
)
from sfir_backend.api.v1.routes import api_router, documentation as documentation_routes
from sfir_backend.domain.documentation.models import (
    DocumentationFormat,
    DocumentationPage,
    DocumentationReport,
    GenerateRequest,
    ReportType,
    Section,
)
from sfir_backend.domain.graph.models import Graph as DomainGraph
from sfir_backend.infrastructure.documentation.engine import DocumentationEngine


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def user_id() -> uuid.UUID:
    return uuid.uuid4()


async def no_org_id() -> None:
    return None


@pytest.fixture
def mock_rbac() -> AsyncMock:
    rbac = AsyncMock()
    rbac.require_permission = AsyncMock()
    return rbac


@pytest.fixture
def mock_docs_engine() -> MagicMock:
    engine = MagicMock(spec=DocumentationEngine)
    type(engine).graph = PropertyMock(return_value=DomainGraph())
    return engine


@pytest.fixture
def mock_graph_service() -> AsyncMock:
    svc = AsyncMock()
    svc.build_graph = AsyncMock(return_value=DomainGraph())
    return svc


@pytest.fixture
def app(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    mock_rbac: AsyncMock,
    mock_docs_engine: MagicMock,
    mock_graph_service: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    application = FastAPI()
    application.include_router(api_router)

    async def inline_to_thread(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(documentation_routes.asyncio, "to_thread", inline_to_thread)

    async def override_current_org_id() -> uuid.UUID:
        return org_id

    async def override_current_user_id() -> uuid.UUID:
        return user_id

    async def override_rbac_service() -> AsyncMock:
        return mock_rbac

    async def override_documentation_engine() -> MagicMock:
        return mock_docs_engine

    async def override_graph_service() -> AsyncMock:
        return mock_graph_service

    application.dependency_overrides[get_current_org_id] = override_current_org_id
    application.dependency_overrides[get_current_user_id] = override_current_user_id
    application.dependency_overrides[get_rbac_service] = override_rbac_service
    application.dependency_overrides[get_documentation_engine] = override_documentation_engine
    application.dependency_overrides[get_graph_service] = override_graph_service

    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestListDocumentation:
    async def test_list_returns_paginated_items(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        pages = [
            DocumentationPage(
                id="p1", component_key="object:Account",
                component_type="object", api_name="Account",
                sections=[Section(title="Overview", content="Account object")],
            ),
            DocumentationPage(
                id="p2", component_key="object:Contact",
                component_type="object", api_name="Contact",
                sections=[Section(title="Overview", content="Contact object")],
            ),
        ]
        report = DocumentationReport(
            id="r1", title="Inventory",
            report_type=ReportType.ARCHITECTURE,
            pages=pages,
        )
        mock_docs_engine.component_inventory.return_value = report

        response = await client.get("/api/v1/documentation")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2
        assert data["items"][0]["component_name"] == "Account"

    async def test_list_empty_when_no_org(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id
        response = await client.get("/api/v1/documentation")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_list_pagination(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        pages = [
            DocumentationPage(
                id=f"p{i}", component_key=f"type:Comp{i}",
                component_type="type", api_name=f"Comp{i}",
            )
            for i in range(5)
        ]
        report = DocumentationReport(id="r1", pages=pages)
        mock_docs_engine.component_inventory.return_value = report

        response = await client.get("/api/v1/documentation?limit=2&offset=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2

    async def test_list_search_filters_by_name(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        pages = [
            DocumentationPage(
                id="p1", component_key="object:Account",
                component_type="object", api_name="Account",
            ),
            DocumentationPage(
                id="p2", component_key="object:Contact",
                component_type="object", api_name="Contact",
            ),
            DocumentationPage(
                id="p3", component_key="flow:MyFlow",
                component_type="flow", api_name="MyFlow",
            ),
        ]
        report = DocumentationReport(id="r1", pages=pages)
        mock_docs_engine.component_inventory.return_value = report

        response = await client.get("/api/v1/documentation?search=count")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["component_name"] == "Account"

    async def test_list_sort_by_type(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        pages = [
            DocumentationPage(
                id="p1", component_key="object:Account",
                component_type="object", api_name="Account",
            ),
            DocumentationPage(
                id="p2", component_key="flow:MyFlow",
                component_type="flow", api_name="MyFlow",
            ),
            DocumentationPage(
                id="p3", component_key="object:Contact",
                component_type="object", api_name="Contact",
            ),
        ]
        report = DocumentationReport(id="r1", pages=pages)
        mock_docs_engine.component_inventory.return_value = report

        response = await client.get("/api/v1/documentation?sort_by=type")
        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["component_name"] == "MyFlow"
        assert data["items"][1]["component_name"] == "Account"
        assert data["items"][2]["component_name"] == "Contact"

    async def test_list_search_no_match(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        pages = [
            DocumentationPage(
                id="p1", component_key="object:Account",
                component_type="object", api_name="Account",
            ),
        ]
        report = DocumentationReport(id="r1", pages=pages)
        mock_docs_engine.component_inventory.return_value = report

        response = await client.get("/api/v1/documentation?search=zzz")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0


class TestGenerateDocumentation:
    async def test_generate_returns_report(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        page = DocumentationPage(
            id="p1", component_key="object:Account",
            component_type="object", api_name="Account",
        )
        report = DocumentationReport(
            id="r1", title="Generated",
            pages=[page],
            format=DocumentationFormat.MARKDOWN,
            generated_at=datetime.now(UTC),
        )
        mock_docs_engine.generate.return_value = report

        response = await client.post(
            "/api/v1/documentation/generate",
            json={"component_ids": ["object:Account"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["total_components"] == 1

    async def test_generate_raises_400_without_org(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id
        response = await client.post(
            "/api/v1/documentation/generate",
            json={"component_ids": ["object:Account"]},
        )
        assert response.status_code == 400

    async def test_generate_with_metadata_types(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        inventory_pages = [
            DocumentationPage(
                id="p1", component_key="object:Account",
                component_type="object", api_name="Account",
            ),
        ]
        inventory = DocumentationReport(id="inv", pages=inventory_pages)
        mock_docs_engine.component_inventory.return_value = inventory
        report = DocumentationReport(
            id="r1", title="Generated",
            pages=inventory_pages,
        )
        mock_docs_engine.generate.return_value = report

        response = await client.post(
            "/api/v1/documentation/generate",
            json={"metadata_types": ["object"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_components"] == 1

    async def test_generate_calls_engine_with_correct_request(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        report = DocumentationReport(id="r1", pages=[])
        mock_docs_engine.generate.return_value = report

        await client.post(
            "/api/v1/documentation/generate",
            json={
                "component_ids": ["object:Account"],
                "include_dependencies": False,
                "format": "html",
            },
        )

        call_args = mock_docs_engine.generate.call_args
        assert call_args is not None
        req: GenerateRequest = call_args[0][0]
        assert req.component_keys == ["object:Account"]
        assert req.format == DocumentationFormat.HTML


class TestExportDocumentation:
    async def test_export_returns_content(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        mock_docs_engine.metadata_report.return_value = DocumentationReport(id="r1", pages=[])
        mock_docs_engine.export_report.return_value = "# Metadata Report"

        response = await client.get("/api/v1/documentation/export?format=markdown")
        assert response.status_code == 200
        data = response.json()
        assert data["format"] == "markdown"
        assert data["content"] == "# Metadata Report"
        assert "filename" in data
        assert data["total_components"] == 0

    async def test_export_invalid_format(
        self,
        client: AsyncClient,
    ) -> None:
        response = await client.get("/api/v1/documentation/export?format=pdf")
        assert response.status_code == 422


class TestGetComponentDocumentation:
    async def test_get_returns_item(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        page = DocumentationPage(
            id="p1", component_key="object:Account",
            component_type="object", api_name="Account",
            generated_at=datetime.now(UTC),
        )
        mock_docs_engine.generate_single.return_value = page

        response = await client.get("/api/v1/documentation/object/Account")
        assert response.status_code == 200
        data = response.json()
        assert data["component_type"] == "object"
        assert data["component_name"] == "Account"

    async def test_get_returns_404_when_missing(
        self,
        client: AsyncClient,
        mock_docs_engine: MagicMock,
    ) -> None:
        mock_docs_engine.generate_single.side_effect = Exception("Not found")

        response = await client.get("/api/v1/documentation/object/NonExistent")
        assert response.status_code == 500

    async def test_get_returns_400_without_org(
        self,
        client: AsyncClient,
        app: FastAPI,
    ) -> None:
        app.dependency_overrides[get_current_org_id] = no_org_id

        response = await client.get("/api/v1/documentation/object/Account")
        assert response.status_code == 400
