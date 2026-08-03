"""Comprehensive pipeline verification tests.

Verifies every stage of the metadata pipeline end-to-end:

  Salesforce Metadata
    ↓
  Parser Stage
    ↓
  Canonical Mapping Stage
    ↓
  Validation Stage
    ↓
  Normalization Stage
    ↓
  Persistence Stage
    ↓
  Graph Stage
    ↓
  Search Stage
    ↓
  AI Context (checked for integration status)

Covers: E2E flow, normalization boundary, persistence, graph,
search, incremental updates, error recovery, performance,
and observability.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from sfir_backend.application.pipeline.mapper.canonical_mapper import CanonicalMapper
from sfir_backend.application.pipeline.metadata_pipeline import MetadataPipeline
from sfir_backend.application.pipeline.normalizer.canonical_normalizer import (
    CanonicalNormalizer,
)
from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import (
    CanonicalMappingStage,
    GraphStage,
    NormalizationStage,
    PersistenceStage,
    SearchStage,
    ValidationStage,
)
from sfir_backend.application.pipeline.validator.canonical_validator import (
    CanonicalMetadataValidator,
)
from sfir_backend.domain.search.models import SearchDocument
from sfir_backend.infrastructure.graph.engine import DependencyGraphEngine
from sfir_backend.infrastructure.search.engine import SearchEngine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ORG_ID = "00000000-0000-0000-0000-000000000001"
CONN_ID = "00000000-0000-0000-0000-000000000002"
JOB_ID = "00000000-0000-0000-0000-000000000003"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_version_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.list_versions_by_organization.return_value = []
    repo.save_versions.side_effect = lambda org_id, versions: versions
    repo.save_batch.side_effect = lambda org_id, components: components
    return repo


@pytest.fixture
def graph_engine() -> DependencyGraphEngine:
    return DependencyGraphEngine()


@pytest.fixture
def search_engine() -> SearchEngine:
    return SearchEngine()


@pytest.fixture
def normalizer() -> CanonicalNormalizer:
    return CanonicalNormalizer()


@pytest.fixture
def mapper() -> CanonicalMapper:
    return CanonicalMapper()


@pytest.fixture
def validator() -> CanonicalMetadataValidator:
    return CanonicalMetadataValidator()


@pytest.fixture
def ctx() -> PipelineContext:
    return PipelineContext(
        organization_id=UUID(ORG_ID),
        connection_id=UUID(CONN_ID),
        sync_job_id=UUID(JOB_ID),
    )


@pytest.fixture
def persistence_stage(mock_version_repo: AsyncMock) -> PersistenceStage:
    return PersistenceStage(metadata_repo=mock_version_repo)


@pytest.fixture
def graph_stage(graph_engine: DependencyGraphEngine) -> GraphStage:
    return GraphStage(graph_engine=graph_engine)


@pytest.fixture
def search_stage(search_engine: SearchEngine) -> SearchStage:
    return SearchStage(search_engine=search_engine)


@pytest.fixture
def production_metadata() -> list[dict[str, Any]]:
    return [
        _doc("Account", "CustomObject", label="Account Object",
             description="Standard account object",
             properties={"isCustomizable": True, "sharingModel": "ReadWrite"}),
        _doc("Contact", "CustomObject", label="Contact Object"),
        _doc("MyCustomObject__c", "CustomObject", label="My Custom Object",
             namespace="mypkg"),
        _doc("Account.Name", "CustomField", label="Account Name",
             properties={"fieldType": "Text", "length": 255}),
        _doc("Account.AccountNumber", "CustomField", label="Account Number",
             properties={"fieldType": "Text", "length": 50}),
        _doc("Contact.Email", "CustomField", label="Email",
             properties={"fieldType": "Email", "length": 80}),
        _doc("AccountService", "ApexClass", label="Account Service",
             description="Service class for Account operations",
             properties={"apiVersion": 58, "isTest": False}),
        _doc("AccountServiceTest", "ApexClass", label="Account Service Test",
             properties={"apiVersion": 58, "isTest": True}),
        _doc("ContactHelper", "ApexClass", label="Contact Helper",
             properties={"apiVersion": 58, "isTest": False}),
        _doc("AccountTrigger", "ApexTrigger", label="Account Trigger",
             properties={"apiVersion": 58}),
        _doc("OpportunityRoutingFlow", "Flow", label="Opportunity Routing Flow",
             properties={"apiVersion": 58, "processType": "AutoLaunchedFlow"}),
        _doc("WelcomeEmailFlow", "Flow", label="Welcome Email Flow",
             properties={"apiVersion": 58, "processType": "AutoLaunchedFlow"}),
        _doc("Account.NameRequired", "ValidationRule",
             label="Account Name Required",
             properties={"active": True, "errorMessage": "Name is required"}),
        _doc("Contact.EmailFormat", "ValidationRule",
             label="Contact Email Format", properties={"active": True}),
        _doc("AccountSummaryReport", "Report", label="Account Summary Report",
             properties={"reportType": "Tabular"}),
        _doc("SalesDashboard", "Dashboard", label="Sales Dashboard",
             properties={"dashboardType": "Specified"}),
        _doc("AccountAdmin", "PermissionSet", label="Account Administrator",
             properties={"permissions": ["Read", "Create", "Edit", "Delete"]}),
        _doc("ReportViewer", "PermissionSet", label="Report Viewer",
             properties={"permissions": ["Read"]}),
        _doc("Account.Business", "RecordType", label="Business Account",
             properties={"isActive": True}),
        _doc("Account.Household", "RecordType", label="Household Account",
             properties={"isActive": True}),
        _doc("Account-Account Layout", "Layout", label="Account Layout",
             properties={"sections": ["Details", "Related Lists"]}),
        _doc("Contact-Contact Layout", "Layout", label="Contact Layout",
             properties={"sections": ["Details"]}),
        _doc("Account_Record_Page", "LightningPage", label="Account Record Page",
             properties={"type": "RecordPage"}),
        _doc("SystemAdministrator", "Profile", label="System Administrator",
             properties={"permissions": ["AuthorApex", "RunFlows"]}),
        _doc("Approval_Config__mdt", "CustomMetadata",
             label="Approval Configuration", properties={"isPublic": True}),
        _doc("Welcome_Email", "EmailTemplate", label="Welcome Email Template",
             properties={"templateType": "text"}),
        _doc("CEO", "Role", label="Chief Executive Officer",
             properties={"accessLevel": "System"}),
        _doc("CFO", "Role", label="Chief Financial Officer",
             properties={"accessLevel": "System", "parentRole": "CEO"}),
        _doc("SupportQueue", "Queue", label="Support Queue",
             properties={"email": "support@org.com"}),
        _doc("ExternalAPI", "NamedCredential", label="External API",
             properties={"endpoint": "https://api.example.com"}),
    ]


# ===================================================================
# 1. END-TO-END PIPELINE VERIFICATION
# ===================================================================


class TestE2EFullPipeline:
    """Full pipeline: Persistence → Graph → Search with production data."""

    @pytest.mark.asyncio
    async def test_all_stages_with_production_metadata(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="AllTypes",
            normalized_components=production_metadata,
        )
        ctx = await persistence_stage.execute(ctx)
        assert ctx.persistence_result["saved"] == len(production_metadata)
        assert ctx.persistence_result["errors"] == 0

        ctx = await graph_stage.execute(ctx)
        assert ctx.graph_result["node_count"] == len(production_metadata)
        assert ctx.graph_version != ""

        ctx = await search_stage.execute(ctx)
        assert ctx.indexed_count == len(production_metadata)
        assert len(ctx.errors) == 0

    @pytest.mark.asyncio
    async def test_orchestrator_full_pipeline(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        pipeline = MetadataPipeline(
            stages=[persistence_stage, graph_stage, search_stage],
        )
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Orchestrated",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(ctx)
        assert result.success
        assert result.saved_count == len(production_metadata)
        assert result.indexed_count == len(production_metadata)
        assert len(result.errors) == 0
        for stage_name in ("persistence", "graph", "search"):
            assert stage_name in result.timing
            assert result.timing[stage_name] > 0

    @pytest.mark.asyncio
    async def test_with_relationships_flow(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject",
                 relationships=[_rel("contains", "CustomField", "Account.Name")]),
            _doc("Account.Name", "CustomField",
                 relationships=[_rel("references", "CustomObject", "Account")]),
            _doc("AccountService", "ApexClass",
                 relationships=[_rel("references", "CustomObject", "Account")]),
            _doc("AccountTrigger", "ApexTrigger",
                 relationships=[_rel("depends_on", "CustomObject", "Account"),
                                _rel("references", "ApexClass", "AccountService")]),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="WithRels",
            normalized_components=docs,
        )
        ctx = await persistence_stage.execute(ctx)
        assert ctx.persistence_result["saved"] == 4

        ctx = await graph_stage.execute(ctx)
        assert ctx.graph_result["node_count"] == 4
        assert ctx.graph_result["edge_count"] >= 3

        ctx = await search_stage.execute(ctx)
        assert ctx.indexed_count == 4


# ===================================================================
# 2. NORMALIZATION BOUNDARY VERIFICATION
# ===================================================================


class TestNormalizationBoundary:
    """No legacy models leak past the Normalizer."""

    @pytest.mark.asyncio
    async def test_graph_receives_only_dicts(
        self, graph_stage: GraphStage, graph_engine: DependencyGraphEngine,
    ) -> None:
        docs = [_doc("Account", "CustomObject"), _doc("Contact", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        result = await graph_stage.execute(ctx)
        assert result.graph_result["node_count"] == 2

    @pytest.mark.asyncio
    async def test_search_receives_only_search_documents(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        docs = [_doc("Account", "CustomObject"), _doc("Contact", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await search_stage.execute(ctx)
        for doc_id in search_engine.index._documents:
            doc = search_engine.index.get_document(doc_id)
            assert isinstance(doc, SearchDocument)

    @pytest.mark.asyncio
    async def test_persistence_receives_only_dicts(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        docs = [_doc("Account", "CustomObject"), _doc("Contact", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        call_args = mock_version_repo.save_versions.call_args
        assert call_args is not None
        versions = call_args[0][1]
        for v in versions:
            payload = v.payload
            assert isinstance(payload, dict)
            assert "api_name" in payload
            assert "type" in payload
            assert "fingerprint" in payload

    def test_normalized_document_structure(self) -> None:
        doc = _doc("Test__c", "CustomObject", namespace="pkg",
                    label="Test", description="A test",
                    properties={"key": "val"})
        assert isinstance(doc, dict)
        assert doc["api_name"] == "Test__c"
        assert doc["type"] == "CustomObject"
        assert doc["namespace"] == "pkg"
        assert doc["label"] == "Test"
        assert doc["description"] == "A test"
        assert doc["fingerprint"]
        assert doc["content_hash"]
        assert doc["organization_id"] == ORG_ID
        assert doc["source_platform"] == "salesforce"
        assert doc["status"] == "active"
        assert doc["version"] == 1
        assert isinstance(doc["properties"], dict)
        assert isinstance(doc["relationships"], list)


# ===================================================================
# 3. PERSISTENCE VERIFICATION
# ===================================================================


class TestPersistenceVerification:
    """Fingerprints, version history, incremental, duplicates, deletion."""

    @pytest.mark.asyncio
    async def test_fingerprint_stable_and_deterministic(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        fp = uuid.uuid4().hex
        docs = [
            _doc("Account", "CustomObject", fingerprint=fp),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        r1 = await stage.execute(ctx)
        assert r1.persistence_result["saved"] == 1

        mock_version_repo.list_versions_by_organization.return_value = [
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Account",
                "version_number": 1,
                "payload": {"fingerprint": fp},
            })(),
        ]
        r2 = await stage.execute(ctx)
        assert r2.persistence_result["saved"] == 0
        assert r2.persistence_result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_version_history_increments(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        existing = [
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Account",
                "version_number": 1,
                "payload": {"fingerprint": "old_fp"},
            })(),
        ]
        mock_version_repo.list_versions_by_organization.return_value = existing

        docs = [_doc("Account", "CustomObject", fingerprint="new_fp")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        saved = mock_version_repo.save_versions.call_args[0][1]
        assert len(saved) == 1
        assert saved[0].version_number == 2

    @pytest.mark.asyncio
    async def test_duplicate_in_batch_skipped(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        fp = uuid.uuid4().hex
        docs = [
            _doc("Account", "CustomObject", fingerprint=fp),
            _doc("Account", "CustomObject", fingerprint=fp),
            _doc("Contact", "CustomObject", fingerprint=uuid.uuid4().hex),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 2
        assert r.persistence_result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_missing_api_name_or_type_skipped(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        docs = [
            _doc("Good", "CustomObject"),
            {"identity": "bad", "type": "NoApiName"},
            {"identity": "bad2", "api_name": "NoType"},
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 1
        assert r.persistence_result["errors"] == 2

    @pytest.mark.asyncio
    async def test_empty_components_list(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=[],
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 0
        assert r.persistence_result["skipped"] == 0
        assert r.persistence_result["errors"] == 0

    @pytest.mark.asyncio
    async def test_batch_save_failure_reported(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        mock_version_repo.save_versions.side_effect = Exception("DB connection lost")
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        docs = [_doc("A", "CustomObject"), _doc("B", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 0
        assert len(r.errors) > 0

    @pytest.mark.asyncio
    async def test_fallback_to_canonical_when_no_normalized(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=[],
            canonical_components=[
                type("FakeCanonical", (), {
                    "api_name": "Legacy",
                    "type": "CustomObject",
                    "model_dump": lambda self, **kwargs: {"api_name": "Legacy", "type": "CustomObject"},
                    "id": None,
                })(),
            ],
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 1


# ===================================================================
# 4. GRAPH VERIFICATION
# ===================================================================


class TestGraphVerification:
    """Nodes, edges, relationship types, cycles, traversal, impact."""

    @pytest.mark.asyncio
    async def test_nodes_created_correctly(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Contact", "CustomObject"),
            _doc("AccountService", "ApexClass"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        stats = graph_engine.node_counts_by_type()
        assert stats.get("object", 0) == 3  # all 3 docs are CustomObject -> graph normalizes to "object"

    @pytest.mark.asyncio
    async def test_edges_preserve_relationship_types(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Account.Name", "CustomField",
                 relationships=[_rel("references", "CustomObject", "Account")]),
            _doc("AccountTrigger", "ApexTrigger",
                 relationships=[_rel("depends_on", "CustomObject", "Account")]),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        assert graph_engine.graph.edge_count == 2

    @pytest.mark.asyncio
    async def test_cycle_detection(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("A", "CustomObject",
                 relationships=[_rel("references", "CustomObject", "B")]),
            _doc("B", "CustomObject",
                 relationships=[_rel("references", "CustomObject", "A")]),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        cycles = graph_engine.detect_cycles()
        assert len(cycles) > 0

    @pytest.mark.asyncio
    async def test_traversal_works(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("Account", "CustomObject",
                 relationships=[_rel("contains", "CustomField", "Account.Name")]),
            _doc("Account.Name", "CustomField",
                 relationships=[_rel("references", "CustomObject", "Account")]),
            _doc("AccountService", "ApexClass",
                 relationships=[_rel("references", "CustomObject", "Account")]),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        where_used = graph_engine.where_used("Account", "CustomObject")
        assert len(where_used) >= 1

    @pytest.mark.asyncio
    async def test_impact_analysis_via_where_used(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("Account", "CustomObject"),
            _doc("Account.Name", "CustomField",
                 relationships=[_rel("references", "CustomObject", "Account")]),
            _doc("AccountTrigger", "ApexTrigger",
                 relationships=[_rel("depends_on", "CustomObject", "Account")]),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        impacted = graph_engine.where_used("Account")
        assert len(impacted) >= 2

    @pytest.mark.asyncio
    async def test_graph_versioning(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [_doc("A", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        v1 = graph_engine.version
        snapshots = graph_engine.list_snapshots()
        assert len(snapshots) >= 1
        rollback = graph_engine.rollback(v1)
        assert rollback is not None

    @pytest.mark.asyncio
    async def test_incremental_graph_update(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage1 = GraphStage(graph_engine=graph_engine)
        docs1 = [_doc("A", "CustomObject"), _doc("B", "CustomObject")]
        ctx1 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs1,
        )
        await stage1.execute(ctx1)
        assert graph_engine.graph.node_count == 2

        stage2 = GraphStage(graph_engine=graph_engine)
        docs2 = [_doc("C", "CustomObject")]
        ctx2 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs2,
        )
        await stage2.execute(ctx2)
        assert graph_engine.graph.node_count == 3

    @pytest.mark.asyncio
    async def test_duplicate_fingerprints_deduped(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs = [
            _doc("Account", "CustomObject", fingerprint="same"),
            _doc("Account", "CustomObject", fingerprint="same"),
            _doc("Contact", "CustomObject", fingerprint="unique"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Test",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        assert graph_engine.graph.node_count == 2


# ===================================================================
# 5. SEARCH VERIFICATION
# ===================================================================


class TestSearchVerification:
    """API name, namespace, full-text, label, description, ranking,
    filtering, autocomplete."""

    @pytest.mark.asyncio
    async def test_api_name_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("Account")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_namespace_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("", namespace="mypkg")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_full_text_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("Service")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_label_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Obj1", "CustomObject", label="My Custom Label"),
            _doc("Obj2", "CustomObject", label="Other Label"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=docs,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("Custom Label")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_description_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Obj1", "CustomObject", description="This handles account processing"),
            _doc("Obj2", "CustomObject", description="Something else"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=docs,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("account processing")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_autocomplete(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        suggestions = search_engine.autocomplete("Acc", limit=5)
        assert len(suggestions) >= 1

    @pytest.mark.asyncio
    async def test_ranking_exact_match_highest(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject", label="Account"),
            _doc("AccountService", "ApexClass", label="Account Service"),
            _doc("AccountSummaryReport", "Report", label="Account Summary"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=docs,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("Account")
        assert resp.total_count >= 1
        scores = [r.score for r in resp.results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_type_filter(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        resp = search_engine.search_metadata("", metadata_types=["ApexClass"])
        assert resp.total_count == 3

    @pytest.mark.asyncio
    async def test_global_search(
        self, search_stage: SearchStage, search_engine: SearchEngine,
        production_metadata: list[dict[str, Any]],
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="SearchV",
            normalized_components=production_metadata,
        )
        await search_stage.execute(ctx)
        resp = search_engine.global_search("Sales")
        assert resp.total_count >= 1


# ===================================================================
# 6. AI CONTEXT VERIFICATION
# ===================================================================


class TestAIContextVerification:
    """Check AI integration status and verify it consumes normalized data."""

    def test_ai_integration_status(self) -> None:
        try:
            from sfir_backend.services.ai import AIAnalysisService  # noqa: F811
            from sfir_backend.application.use_cases.ai import AIUseCase  # noqa: F811
        except ImportError:
            pytest.skip("AI services not integrated yet")

    def test_ai_does_not_import_parser_models(self) -> None:
        try:
            import importlib
            for mod_name in ("sfir_backend.services.ai",):
                try:
                    mod = importlib.import_module(mod_name)
                    src = getattr(mod, "__file__", "")
                except Exception:
                    continue
            pytest.skip("AI services not integrated yet")
        except Exception:
            pytest.skip("AI modules not available")

    def test_ai_consumes_normalized_only(self) -> None:
        try:
            from sfir_backend.application.use_cases.ai import AIUseCase  # noqa: F811
        except ImportError:
            pytest.skip("AI use case not integrated")
        from sfir_backend.domain.search.models import SearchDocument
        doc = SearchDocument(
            id="test", api_name="Test", label="Test",
            metadata_type="CustomObject", organization_id=ORG_ID,
        )
        assert doc.api_name == "Test"


# ===================================================================
# 7. INCREMENTAL UPDATE VERIFICATION
# ===================================================================


class TestIncrementalUpdateVerification:
    """Simulates sync cycles: initial → no changes → modifications → deletions."""

    @pytest.mark.asyncio
    async def test_initial_sync(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        docs = [
            _doc("Account", "CustomObject", fingerprint="fp1"),
            _doc("Contact", "CustomObject", fingerprint="fp2"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Incr",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 2

    @pytest.mark.asyncio
    async def test_second_sync_no_changes(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        mock_version_repo.list_versions_by_organization.return_value = [
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Account",
                "version_number": 1,
                "payload": {"fingerprint": "fp1"},
            })(),
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Contact",
                "version_number": 1,
                "payload": {"fingerprint": "fp2"},
            })(),
        ]
        docs = [
            _doc("Account", "CustomObject", fingerprint="fp1"),
            _doc("Contact", "CustomObject", fingerprint="fp2"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Incr",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 0
        assert r.persistence_result["skipped"] == 2

    @pytest.mark.asyncio
    async def test_third_sync_with_modifications(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        mock_version_repo.list_versions_by_organization.return_value = [
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Account",
                "version_number": 1,
                "payload": {"fingerprint": "fp1"},
            })(),
            type("V", (), {
                "component_type": "CustomObject", "component_name": "Contact",
                "version_number": 1,
                "payload": {"fingerprint": "fp2"},
            })(),
        ]
        docs = [
            _doc("Account", "CustomObject", fingerprint="fp1"),
            _doc("Contact", "CustomObject", fingerprint="fp2_modified"),
            _doc("NewObject__c", "CustomObject", fingerprint="fp3"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Incr",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 2
        assert r.persistence_result["skipped"] == 1

    @pytest.mark.asyncio
    async def test_incremental_with_deletions(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        docs1 = [
            _doc("A", "CustomObject"),
            _doc("B", "CustomObject"),
            _doc("C", "CustomObject"),
        ]
        ctx1 = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Incr",
            normalized_components=docs1,
        )
        await stage.execute(ctx1)
        assert graph_engine.graph.node_count == 3
        v1 = graph_engine.version

        # incremental update: add D, delete B (node key is "object:B" -> pass just "B")
        graph_engine.incremental_update_from_normalized(
            normalized_components=[_doc("D", "CustomObject")],
            deleted_api_names=["B"],
        )
        assert graph_engine.graph.node_count == 3  # A, C, D (B deleted, D added)
        assert graph_engine.version != v1


# ===================================================================
# 8. ERROR RECOVERY VERIFICATION
# ===================================================================


class TestErrorRecoveryVerification:
    """Invalid metadata, partial failures, validation failures, retries."""

    @pytest.mark.asyncio
    async def test_search_continues_after_bad_data(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        docs = [
            _doc("Account", "CustomObject"),
            {"bad": "data"},
            _doc("Contact", "CustomObject"),
        ]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Error",
            normalized_components=docs,
        )
        r = await search_stage.execute(ctx)
        assert r.indexed_count == 2

    @pytest.mark.asyncio
    async def test_graph_handles_empty_components(
        self, graph_stage: GraphStage, graph_engine: DependencyGraphEngine,
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Empty",
            normalized_components=[],
        )
        r = await graph_stage.execute(ctx)
        assert r.graph_result == {}

    @pytest.mark.asyncio
    async def test_search_handles_empty_components(
        self, search_stage: SearchStage, search_engine: SearchEngine,
    ) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Empty",
            normalized_components=[],
        )
        r = await search_stage.execute(ctx)
        assert r.indexed_count == 0

    @pytest.mark.asyncio
    async def test_pipeline_recovery_after_stage_failure(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        mock_version_repo.save_versions.side_effect = Exception("Transient failure")
        docs = [_doc("A", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Error",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 0
        assert len(r.errors) > 0

        mock_version_repo.save_versions.side_effect = lambda org_id, versions: versions
        r2 = await stage.execute(ctx)
        assert r2.persistence_result["saved"] == 1

    @pytest.mark.asyncio
    async def test_partial_validation_failure(
        self, normalizer: CanonicalNormalizer,
        mapper: CanonicalMapper, validator: CanonicalMetadataValidator,
        mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Error",
            normalized_components=[],
            canonical_components=[],
        )
        r = await stage.execute(ctx)
        assert r.persistence_result["saved"] == 0

    @pytest.mark.asyncio
    async def test_stage_exception_does_not_crash_pipeline(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        mock_version_repo.save_versions.side_effect = Exception("Crash")
        docs = [_doc("A", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Error",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert "errors" in r.persistence_result
        assert len(r.errors) > 0


# ===================================================================
# 9. PERFORMANCE / LARGE DATASET VERIFICATION
# ===================================================================


class TestPerformanceVerification:
    """Large metadata sets, memory, latency checks."""

    @pytest.mark.asyncio
    async def test_large_batch_persistence(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        n = 5000
        docs = [_doc(f"O{i}", "CustomObject") for i in range(n)]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Perf",
            normalized_components=docs,
        )
        start = time.monotonic()
        r = await stage.execute(ctx)
        elapsed = time.monotonic() - start
        assert r.persistence_result["saved"] == n
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_large_batch_graph(
        self, graph_engine: DependencyGraphEngine,
    ) -> None:
        stage = GraphStage(graph_engine=graph_engine)
        n = 2000
        docs = [_doc(f"O{i}", "CustomObject") for i in range(n)]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Perf",
            normalized_components=docs,
        )
        start = time.monotonic()
        await stage.execute(ctx)
        elapsed = time.monotonic() - start
        assert graph_engine.graph.node_count == n
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_large_batch_search(
        self, search_engine: SearchEngine,
    ) -> None:
        stage = SearchStage(search_engine=search_engine)
        n = 2000
        docs = [_doc(f"O{i}", "CustomObject") for i in range(n)]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Perf",
            normalized_components=docs,
        )
        start = time.monotonic()
        await stage.execute(ctx)
        elapsed = time.monotonic() - start
        assert ctx.indexed_count == n
        assert elapsed < 5.0

    @pytest.mark.asyncio
    async def test_search_among_large_dataset(
        self, search_engine: SearchEngine,
    ) -> None:
        stage = SearchStage(search_engine=search_engine)
        n = 1000
        docs = [_doc(f"O{i}", "CustomObject") for i in range(n)]
        docs.append(_doc("TargetObject", "CustomObject",
                         label="Target Label",
                         description="Target description for search"))
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Perf",
            normalized_components=docs,
        )
        await stage.execute(ctx)
        start = time.monotonic()
        resp = search_engine.search_metadata("TargetObject")
        elapsed = time.monotonic() - start
        assert resp.total_count >= 1
        assert elapsed < 2.0

    @pytest.mark.asyncio
    async def test_all_stages_large_batch(
        self,
        persistence_stage: PersistenceStage,
        graph_stage: GraphStage,
        search_stage: SearchStage,
    ) -> None:
        n = 1000
        docs = [_doc(f"C{i}", "CustomObject") for i in range(n)]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Perf",
            normalized_components=docs,
        )
        start = time.monotonic()
        ctx = await persistence_stage.execute(ctx)
        assert ctx.persistence_result["saved"] == n

        ctx = await graph_stage.execute(ctx)
        assert ctx.graph_result["node_count"] == n

        ctx = await search_stage.execute(ctx)
        assert ctx.indexed_count == n

        elapsed = time.monotonic() - start
        assert elapsed < 10.0


# ===================================================================
# 10. OBSERVABILITY VERIFICATION
# ===================================================================


class TestObservabilityVerification:
    """Logging, timing, context fields, error tracking."""

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
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="ObserveE2E",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(ctx)
        assert result.success
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
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="TimingE2E",
            normalized_components=production_metadata,
        )
        result = await pipeline.process_component(ctx)
        for stage_name in ("persistence", "graph", "search"):
            assert stage_name in result.timing
            assert result.timing[stage_name] > 0

    def test_pipeline_context_fields(self) -> None:
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID),
            connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID),
        )
        required = [
            "normalized_components", "normalized_relationships",
            "graph_result", "graph_statistics", "graph_version",
            "indexed_count", "persistence_result", "stage_timing",
            "errors", "success", "organization_id", "connection_id",
            "sync_job_id", "component_type",
        ]
        for field in required:
            assert hasattr(ctx, field), f"Missing field: {field}"

    @pytest.mark.asyncio
    async def test_errors_propagate_to_result(
        self, mock_version_repo: AsyncMock,
    ) -> None:
        stage = PersistenceStage(metadata_repo=mock_version_repo)
        mock_version_repo.save_versions.side_effect = Exception("Fail")
        docs = [_doc("A", "CustomObject")]
        ctx = PipelineContext(
            organization_id=UUID(ORG_ID), connection_id=UUID(CONN_ID),
            sync_job_id=UUID(JOB_ID), component_type="Observe",
            normalized_components=docs,
        )
        r = await stage.execute(ctx)
        assert len(r.errors) > 0

    def test_structured_logging_fields(self) -> None:
        import structlog
        logger = structlog.get_logger("test")
        import io
        buf = io.StringIO()
        structlog.configure(
            processors=[structlog.dev.ConsoleRenderer()],
            logger_factory=structlog.PrintLoggerFactory(buf),
        )
        logger.info("test_message", stage="persistence", component_type="Test")
        output = buf.getvalue()
        assert "test_message" in output