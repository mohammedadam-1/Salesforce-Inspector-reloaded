"""End-to-end pipeline integration tests.

Verifies the complete metadata pipeline end-to-end:

  NormalizedDocument
    ↓
  PersistenceStage  (with mocked repository)
    ↓
  GraphStage
    ↓
  SearchStage
    ↓
  SearchEngine

Each downstream consumer receives only normalized metadata.
No legacy models (MetadataComponent, parser models, canonical models)
reach Persistence, Graph, or Search.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from sfir_backend.application.pipeline.metadata_pipeline import MetadataPipeline
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import (
    GraphStage,
    PersistenceStage,
    SearchStage,
)
from sfir_backend.domain.search.models import SearchDocument
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.search.engine import SearchEngine


# =======================================================================
# Realistic Normalized Document Fixtures
#
# These represent what the Normalizer produces for various Salesforce
# metadata types. Each dict models the output of
#   NormalizedDocument.model_dump(mode="json")
# =======================================================================

ORG_ID = "00000000-0000-0000-0000-000000000001"
CONN_ID = "00000000-0000-0000-0000-000000000002"
JOB_ID = "00000000-0000-0000-0000-000000000003"


def _doc(
    api_name: str,
    type_name: str,
    label: str | None = None,
    description: str | None = None,
    namespace: str | None = None,
    status: str = "active",
    fingerprint: str | None = None,
    properties: dict | None = None,
    created_at: str | None = "2024-01-01T00:00:00+00:00",
    updated_at: str | None = "2024-06-01T00:00:00+00:00",
    relationships: list[dict] | None = None,
) -> dict[str, Any]:
    fp = fingerprint or uuid.uuid4().hex
    return {
        "identity": uuid.uuid4().hex,
        "api_name": api_name,
        "type": type_name,
        "fingerprint": fp,
        "content_hash": fp,
        "qualified_name": f"{namespace + '__' if namespace else ''}{api_name}",
        "fully_qualified_name": f"{namespace + '__' if namespace else ''}{api_name}",
        "version": 1,
        "status": status,
        "source_platform": "salesforce",
        "organization_id": ORG_ID,
        "label": label or api_name,
        "namespace": namespace,
        "description": description,
        "created_at": created_at,
        "updated_at": updated_at,
        "properties": properties or {},
        "relationships": relationships or [],
    }


def _rel(
    rel_type: str = "references",
    target_type: str = "CustomObject",
    target_api_name: str = "Account",
    target_namespace: str | None = None,
    target_fqdn: str = "Account",
) -> dict[str, Any]:
    return {
        "type": rel_type,
        "target_identity": uuid.uuid4().hex,
        "target_component_key": {
            "type": target_type,
            "api_name": target_api_name,
            "namespace": target_namespace,
        },
        "target_fqdn": target_fqdn,
        "metadata": {},
    }


# ─── Production-like dataset ──────────────────────────────────────


@pytest.fixture
def production_metadata() -> list[dict[str, Any]]:
    return [
        # Custom Objects
        _doc("Account", "CustomObject", label="Account Object",
             description="Standard account object",
             properties={"isCustomizable": True, "sharingModel": "ReadWrite"}),
        _doc("Contact", "CustomObject", label="Contact Object",
             description="Standard contact object"),
        _doc("MyCustomObject__c", "CustomObject", label="My Custom Object",
             namespace="mypkg",
             properties={"isCustomizable": True, "sharingModel": "ReadWrite"}),
        # Fields (children of objects)
        _doc("Account.Name", "CustomField", label="Account Name",
             properties={"fieldType": "Text", "length": 255}),
        _doc("Account.AccountNumber", "CustomField", label="Account Number",
             properties={"fieldType": "Text", "length": 50}),
        _doc("Contact.Email", "CustomField", label="Email",
             properties={"fieldType": "Email", "length": 80}),
        # Apex Classes
        _doc("AccountService", "ApexClass", label="Account Service",
             description="Service class for Account operations",
             properties={"apiVersion": 58, "isTest": False}),
        _doc("AccountServiceTest", "ApexClass", label="Account Service Test",
             description="Tests for AccountService",
             properties={"apiVersion": 58, "isTest": True}),
        _doc("ContactHelper", "ApexClass", label="Contact Helper",
             properties={"apiVersion": 58, "isTest": False}),
        # Apex Triggers
        _doc("AccountTrigger", "ApexTrigger", label="Account Trigger",
             description="Trigger on Account",
             properties={"apiVersion": 58}),
        # Flows
        _doc("OpportunityRoutingFlow", "Flow", label="Opportunity Routing Flow",
             description="Routes opportunities to appropriate teams",
             properties={"apiVersion": 58, "processType": "AutoLaunchedFlow"}),
        _doc("WelcomeEmailFlow", "Flow", label="Welcome Email Flow",
             description="Sends welcome email to new contacts",
             properties={"apiVersion": 58, "processType": "AutoLaunchedFlow"}),
        # Validation Rules
        _doc("Account.NameRequired", "ValidationRule",
             label="Account Name Required",
             description="Account Name must not be blank",
             properties={"active": True, "errorMessage": "Name is required"}),
        _doc("Contact.EmailFormat", "ValidationRule",
             label="Contact Email Format",
             description="Email must contain @",
             properties={"active": True}),
        # Reports & Dashboards
        _doc("AccountSummaryReport", "Report", label="Account Summary Report",
             properties={"reportType": "Tabular"}),
        _doc("SalesDashboard", "Dashboard", label="Sales Dashboard",
             properties={"dashboardType": "Specified"}),
        # Permission Sets
        _doc("AccountAdmin", "PermissionSet", label="Account Administrator",
             description="Full access to Account",
             properties={"permissions": ["Read", "Create", "Edit", "Delete"]}),
        _doc("ReportViewer", "PermissionSet", label="Report Viewer",
             description="View reports only",
             properties={"permissions": ["Read"]}),
        # Record Types
        _doc("Account.Business", "RecordType", label="Business Account",
             properties={"isActive": True}),
        _doc("Account.Household", "RecordType", label="Household Account",
             properties={"isActive": True}),
        # Layouts
        _doc("Account-Account Layout", "Layout", label="Account Layout",
             description="Default Account layout",
             properties={"sections": ["Details", "Related Lists"]}),
        _doc("Contact-Contact Layout", "Layout", label="Contact Layout",
             properties={"sections": ["Details"]}),
        # Lightning Pages
        _doc("Account_Record_Page", "LightningPage", label="Account Record Page",
             description="Lightning record page for Account",
             properties={"type": "RecordPage"}),
        # Profiles
        _doc("SystemAdministrator", "Profile", label="System Administrator",
             properties={"permissions": ["AuthorApex", "RunFlows"]}),
        # Custom Metadata Types
        _doc("Approval_Config__mdt", "CustomMetadata",
             label="Approval Configuration",
             properties={"isPublic": True}),
        # Email Templates
        _doc("Welcome_Email", "EmailTemplate", label="Welcome Email Template",
             description="Welcome email for new users",
             properties={"templateType": "text"}),
        # Roles
        _doc("CEO", "Role", label="Chief Executive Officer",
             properties={"accessLevel": "System"}),
        _doc("CFO", "Role", label="Chief Financial Officer",
             properties={"accessLevel": "System", "parentRole": "CEO"}),
        # Queues
        _doc("SupportQueue", "Queue", label="Support Queue",
             properties={"email": "support@org.com"}),
        # Named Credentials
        _doc("ExternalAPI", "NamedCredential", label="External API",
             properties={"endpoint": "https://api.example.com"}),
    ]


@pytest.fixture
def production_metadata_with_relationships() -> list[dict[str, Any]]:
    return [
        _doc(
            "Account", "CustomObject", label="Account Object",
            relationships=[_rel("contains", "CustomField", "Account.Name")],
        ),
        _doc(
            "Account.Name", "CustomField", label="Account Name",
            relationships=[_rel("references", "CustomObject", "Account")],
        ),
        _doc(
            "AccountService", "ApexClass", label="Account Service",
            relationships=[_rel("references", "CustomObject", "Account")],
        ),
        _doc(
            "AccountTrigger", "ApexTrigger", label="Account Trigger",
            relationships=[_rel("depends_on", "CustomObject", "Account"),
                           _rel("references", "ApexClass", "AccountService")],
        ),
    ]


# =======================================================================
# Fixtures: stages with shared engine state
# =======================================================================


@pytest.fixture
def mock_version_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.list_by_organization.return_value = []
    repo.save_many.side_effect = lambda versions: versions
    return repo


@pytest.fixture
def graph_engine() -> DependencyGraphEngine:
    return DependencyGraphEngine()


@pytest.fixture
def search_engine() -> SearchEngine:
    return SearchEngine()


@pytest.fixture
def persistence_stage(mock_version_repo: AsyncMock) -> PersistenceStage:
    return PersistenceStage(version_repo=mock_version_repo)


@pytest.fixture
def graph_stage(graph_engine: DependencyGraphEngine) -> GraphStage:
    return GraphStage(graph_engine=graph_engine)


@pytest.fixture
def search_stage(search_engine: SearchEngine) -> SearchStage:
    return SearchStage(search_engine=search_engine)


# =======================================================================
# E2E: Full Pipeline with Production Metadata
# =======================================================================


class TestEndToEndPipeline:
    """Verifies the complete pipeline with production-like metadata."""

    @pytest.mark.asyncio
    async def test_full_pipeline_all_metadata_types(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="AllTypes",
            normalized_components=production_metadata,
        )

        # Stage 1: Persistence
        context = await persistence_stage.execute(context)
        assert context.persistence_result["saved"] == len(production_metadata)
        assert context.persistence_result["errors"] == 0
        assert len(context.errors) == 0

        # Stage 2: Graph
        context = await graph_stage.execute(context)
        assert context.graph_result["node_count"] == len(production_metadata)
        assert context.graph_result["edge_count"] == 0
        assert context.graph_version != ""

        # Stage 3: Search
        context = await search_stage.execute(context)
        assert context.indexed_count == len(production_metadata)
        assert len(context.errors) == 0

    @pytest.mark.asyncio
    async def test_full_pipeline_with_relationships(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata_with_relationships: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="WithRelationships",
            normalized_components=production_metadata_with_relationships,
        )

        context = await persistence_stage.execute(context)
        assert context.persistence_result["saved"] == 4

        context = await graph_stage.execute(context)
        assert context.graph_result["node_count"] == 4
        assert context.graph_result["edge_count"] >= 3

        context = await search_stage.execute(context)
        assert context.indexed_count == 4

    @pytest.mark.asyncio
    async def test_pipeline_orchestrator(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        pipeline = MetadataPipeline(
            stages=[persistence_stage, graph_stage, search_stage],
        )
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="Orchestrated",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(context)
        assert result.success
        assert result.saved_count == len(production_metadata)
        assert result.indexed_count == len(production_metadata)
        assert len(result.errors) == 0
        assert "persistence" in result.timing
        assert "graph" in result.timing
        assert "search" in result.timing


# =======================================================================
# E2E: Normalization Boundary Verification
# =======================================================================


class TestNormalizationBoundary:
    """Verifies that no legacy models leak past the Normalizer."""

    @pytest.mark.asyncio
    async def test_graph_receives_only_dicts(
        self,
        graph_stage: GraphStage,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Contact", "CustomObject"),
        ]
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="Test",
            normalized_components=docs,
        )
        result = await graph_stage.execute(context)
        assert result.graph_result["node_count"] == 2
        assert result.graph_result["edge_count"] == 0

    @pytest.mark.asyncio
    async def test_search_receives_only_search_documents(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Contact", "CustomObject"),
        ]
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="Test",
            normalized_components=docs,
        )
        await search_stage.execute(context)
        for doc_id in search_engine.index._documents:
            doc = search_engine.index.get_document(doc_id)
            assert isinstance(doc, SearchDocument)
            assert not hasattr(doc, "metadata_properties") or isinstance(
                doc.metadata_properties, dict
            )

    @pytest.mark.asyncio
    async def test_persistence_receives_only_dicts(
        self,
        mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(version_repo=mock_version_repo)
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Contact", "CustomObject"),
        ]
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
            component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(context)
        call_args = mock_version_repo.save_many.call_args
        assert call_args is not None
        versions = call_args[0][0]
        for v in versions:
            payload = v.payload
            assert isinstance(payload, dict)
            assert "api_name" in payload
            assert "type" in payload
            assert "fingerprint" in payload


# =======================================================================
# E2E: Incremental Update Verification
# =======================================================================


class TestIncrementalUpdates:
    """Simulates real-world sync cycles."""

    @pytest.mark.asyncio
    async def test_initial_sync_then_no_changes(
        self,
        mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(version_repo=mock_version_repo)

        # First sync: persists everything
        mock_version_repo.list_by_organization.return_value = []
        docs1 = [
            _doc("Account", "CustomObject", fingerprint="fp1"),
            _doc("Contact", "CustomObject", fingerprint="fp2"),
        ]
        ctx1 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs1,
        )
        r1 = await stage.execute(ctx1)
        assert r1.persistence_result["saved"] == 2
        assert r1.persistence_result["skipped"] == 0

    @pytest.mark.asyncio
    async def test_second_sync_with_modifications(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(version_repo=mock_version_repo)

        # Build existing state
        existing = [
            type("V", (), {
                "component_type": "CustomObject",
                "component_name": "Account",
                "version_number": 1,
                "payload": {"fingerprint": "fp1"},
            })(),
            type("V", (), {
                "component_type": "CustomObject",
                "component_name": "Contact",
                "version_number": 1,
                "payload": {"fingerprint": "fp2"},
            })(),
        ]
        mock_version_repo.list_by_organization.return_value = existing

        # Account unchanged (same fp), Contact modified (new fp), NewObject added
        docs2 = [
            _doc("Account", "CustomObject", fingerprint="fp1"),
            _doc("Contact", "CustomObject", fingerprint="fp2_modified"),
            _doc("NewObject__c", "CustomObject", fingerprint="fp3"),
        ]
        ctx2 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs2,
        )
        r2 = await stage.execute(ctx2)
        assert r2.persistence_result["saved"] == 2
        assert r2.persistence_result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_incremental_graph_update(
        self,
        graph_engine: DependencyGraphEngine,
        search_engine: SearchEngine,
    ) -> None:
        graph_stage = GraphStage(graph_engine=graph_engine)
        search_stage = SearchStage(search_engine=search_engine)

        # Initial build
        docs1 = [
            _doc("Account", "CustomObject",
                 relationships=[_rel("contains", "CustomField", "Account.Name")]),
            _doc("Account.Name", "CustomField"),
            _doc("Contact", "CustomObject"),
        ]
        ctx1 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs1,
        )
        await graph_stage.execute(ctx1)
        assert graph_engine.graph.node_count == 3
        assert graph_engine.graph.edge_count == 1
        version1 = graph_engine.version

        # Incremental add
        docs2 = [_doc("Opportunity", "CustomObject")]
        ctx2 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs2,
        )
        graph_stage2 = GraphStage(graph_engine=graph_engine)
        await graph_stage2.execute(ctx2)
        assert graph_engine.graph.node_count == 4
        assert graph_engine.version != version1


# =======================================================================
# E2E: Search Verification
# =======================================================================


class TestSearchEndToEnd:
    """Verifies search functionality after pipeline processing."""

    @pytest.mark.asyncio
    async def test_api_name_search_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.search_metadata("Account")
        assert response.total_count >= 1

        response = search_engine.search_metadata("ContactHelper")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_namespace_search_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.search_metadata("", namespace="mypkg")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_metadata_type_filter_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.search_metadata("", metadata_types=["ApexClass"])
        assert response.total_count == 3

    @pytest.mark.asyncio
    async def test_full_text_search_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.search_metadata("Service")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_autocomplete_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        suggestions = search_engine.autocomplete("Acc", limit=5)
        assert len(suggestions) >= 1

    @pytest.mark.asyncio
    async def test_global_search_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.global_search("Sales")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_search_ranking_after_pipeline(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchE2E",
            normalized_components=production_metadata,
        )
        await search_stage.execute(context)

        response = search_engine.search_metadata("Account")
        assert response.total_count >= 1
        scores = [r.score for r in response.results]
        assert scores == sorted(scores, reverse=True)


# =======================================================================
# E2E: Error Recovery
# =======================================================================


class TestErrorRecovery:
    """Verifies pipeline handles failures gracefully."""

    @pytest.mark.asyncio
    async def test_pipeline_continues_after_bad_data(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject"),
            {"bad": "data"},  # type: ignore[dict-item]
            _doc("Contact", "CustomObject"),
        ]
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="ErrorE2E",
            normalized_components=docs,
        )
        result = await search_stage.execute(context)
        assert result.indexed_count == 2
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_search_handles_empty_components(
        self,
        search_stage: SearchStage,
        search_engine: SearchEngine,
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="EmptyE2E",
            normalized_components=[],
        )
        result = await search_stage.execute(context)
        assert result.indexed_count == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_graph_handles_empty_components(
        self,
        graph_stage: GraphStage,
        graph_engine: DependencyGraphEngine,
    ) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="EmptyE2E",
            normalized_components=[],
        )
        result = await graph_stage.execute(context)
        assert result.graph_result == {}
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_graph_handles_duplicate_fingerprints(
        self,
        graph_stage: GraphStage,
        graph_engine: DependencyGraphEngine,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject", fingerprint="same"),
            _doc("Account", "CustomObject", fingerprint="same"),
            _doc("Contact", "CustomObject", fingerprint="unique"),
        ]
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="DedupE2E",
            normalized_components=docs,
        )
        result = await graph_stage.execute(context)
        assert result.graph_result["node_count"] == 2
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_all_stages_handle_large_batch(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
    ) -> None:
        docs = [_doc(f"Component{i}", "CustomObject") for i in range(1000)]
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="LargeE2E",
            normalized_components=docs,
        )

        context = await persistence_stage.execute(context)
        assert context.persistence_result["saved"] == 1000

        context = await graph_stage.execute(context)
        assert context.graph_result["node_count"] == 1000

        context = await search_stage.execute(context)
        assert context.indexed_count == 1000


# =======================================================================
# E2E: Observability Verification
# =======================================================================


class TestObservability:
    """Verifies pipeline observability contracts."""

    @pytest.mark.asyncio
    async def test_pipeline_result_contract(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        pipeline = MetadataPipeline(
            stages=[persistence_stage, graph_stage, search_stage],
        )
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="ObserveE2E",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(context)
        assert result.success
        assert result.component_type == "ObserveE2E"
        assert result.total_count == len(production_metadata)
        assert result.saved_count == len(production_metadata)
        assert result.indexed_count == len(production_metadata)
        assert len(result.timing) == 3
        for stage_name in ("persistence", "graph", "search"):
            assert stage_name in result.timing
            assert result.timing[stage_name] > 0
        assert len(result.errors) == 0
        assert len(result.stage_errors) == 0

    @pytest.mark.asyncio
    async def test_pipeline_timing_recorded(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        pipeline = MetadataPipeline(
            stages=[persistence_stage, graph_stage, search_stage],
        )
        context = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="TimingE2E",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(context)
        assert "persistence" in result.timing
        assert result.timing["persistence"] > 0
        assert "graph" in result.timing
        assert result.timing["graph"] > 0
        assert "search" in result.timing
        assert result.timing["search"] > 0

    def test_pipeline_context_fields_exist(self) -> None:
        context = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
        )
        assert hasattr(context, "normalized_components")
        assert hasattr(context, "normalized_relationships")
        assert hasattr(context, "graph_result")
        assert hasattr(context, "graph_statistics")
        assert hasattr(context, "graph_version")
        assert hasattr(context, "indexed_count")
        assert hasattr(context, "persistence_result")
        assert hasattr(context, "stage_timing")
        assert hasattr(context, "errors")
        assert context.success
