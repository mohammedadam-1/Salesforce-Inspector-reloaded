from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest

from sfir_backend.application.pipeline.pipeline_context import PipelineContext
from sfir_backend.application.pipeline.stages import SearchStage
from sfir_backend.domain.search.models import SearchDocument
from sfir_backend.infrastructure.search.engine import SearchEngine


def _normalized_doc(
    api_name: str = "TestClass",
    type_name: str = "ApexClass",
    identity: str | None = None,
    label: str | None = "Test Class",
    description: str | None = None,
    namespace: str | None = None,
    organization_id: str | None = None,
    status: str = "active",
    created_at: str | None = None,
    updated_at: str | None = None,
    properties: dict | None = None,
    fingerprint: str = "fp123",
) -> dict[str, Any]:
    return {
        "identity": identity or uuid.uuid4().hex,
        "api_name": api_name,
        "type": type_name,
        "fingerprint": fingerprint or uuid.uuid4().hex,
        "content_hash": uuid.uuid4().hex,
        "qualified_name": api_name,
        "fully_qualified_name": api_name,
        "version": 1,
        "status": status,
        "source_platform": "salesforce",
        "organization_id": organization_id or str(uuid.uuid4()),
        "label": label,
        "namespace": namespace,
        "description": description,
        "created_at": created_at,
        "updated_at": updated_at,
        "properties": properties or {},
        "relationships": [],
    }


def _make_context(normalized_components: list[dict] | None = None) -> PipelineContext:
    return PipelineContext(
        organization_id=UUID("00000000-0000-0000-0000-000000000001"),
        connection_id=UUID("00000000-0000-0000-0000-000000000002"),
        sync_job_id=UUID("00000000-0000-0000-0000-000000000003"),
        component_type="ApexClass",
        normalized_components=normalized_components or [],
    )


# ─── _normalized_to_search_document mapping ─────────────────────


class TestNormalizedToSearchDocument:
    def test_basic_mapping(self) -> None:
        doc = _normalized_doc(api_name="Account", type_name="CustomObject", label="Account")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.api_name == "Account"
        assert result.metadata_type == "CustomObject"
        assert result.label == "Account"

    def test_identity_as_id(self) -> None:
        identity = uuid.uuid4().hex
        doc = _normalized_doc(identity=identity)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.id == identity

    def test_id_fallback_when_no_identity(self) -> None:
        doc = _normalized_doc(api_name="MyClass", type_name="ApexClass")
        doc.pop("identity", None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.id == "ApexClass:MyClass"

    def test_label_mapping(self) -> None:
        doc = _normalized_doc(label="My Label")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.label == "My Label"

    def test_label_default_when_none(self) -> None:
        doc = _normalized_doc(label=None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.label == ""

    def test_description_mapping(self) -> None:
        doc = _normalized_doc(description="A test class")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.description == "A test class"

    def test_description_default_when_none(self) -> None:
        doc = _normalized_doc(description=None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.description == ""

    def test_namespace_mapping(self) -> None:
        doc = _normalized_doc(namespace="mypkg")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.namespace == "mypkg"

    def test_namespace_none(self) -> None:
        doc = _normalized_doc(namespace=None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.namespace is None

    def test_organization_id_mapping(self) -> None:
        org_id = str(uuid.uuid4())
        doc = _normalized_doc(organization_id=org_id)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.organization_id == org_id

    def test_status_mapping(self) -> None:
        doc = _normalized_doc(status="inactive")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.status == "inactive"

    def test_status_default(self) -> None:
        doc = _normalized_doc()
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.status == "active"

    def test_created_at_conversion(self) -> None:
        ts = "2024-01-15T10:30:00+00:00"
        doc = _normalized_doc(created_at=ts)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.created_at == datetime.fromisoformat(ts)

    def test_created_at_none(self) -> None:
        doc = _normalized_doc(created_at=None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.created_at is None

    def test_created_at_invalid_returns_none(self) -> None:
        doc = _normalized_doc(created_at="not-a-date")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.created_at is None

    def test_updated_at_conversion(self) -> None:
        ts = "2024-06-20T15:45:00Z"
        doc = _normalized_doc(updated_at=ts)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.updated_at == datetime.fromisoformat(ts)

    def test_updated_at_none(self) -> None:
        doc = _normalized_doc(updated_at=None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.updated_at is None

    def test_properties_to_metadata_properties(self) -> None:
        props = {"key1": "val1", "key2": 42}
        doc = _normalized_doc(properties=props)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.metadata_properties == props

    def test_properties_default_empty(self) -> None:
        doc = _normalized_doc()
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.metadata_properties == {}

    def test_empty_api_name_returns_none(self) -> None:
        doc = _normalized_doc(api_name="")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is None

    def test_empty_type_returns_none(self) -> None:
        doc = _normalized_doc(type_name="")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is None

    def test_missing_api_name_key_returns_none(self) -> None:
        doc = _normalized_doc()
        doc.pop("api_name", None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is None

    def test_missing_type_key_returns_none(self) -> None:
        doc = _normalized_doc()
        doc.pop("type", None)
        result = SearchStage._normalized_to_search_document(doc)
        assert result is None

    def test_whitespace_api_name_returns_none(self) -> None:
        doc = _normalized_doc(api_name="  ")
        result = SearchStage._normalized_to_search_document(doc)
        assert result is None

    def test_all_fields_comprehensive(self) -> None:
        identity = uuid.uuid4().hex
        org_id = str(uuid.uuid4())
        created = "2024-01-01T00:00:00+00:00"
        updated = "2024-06-01T12:00:00+00:00"
        props = {"isManaged": False, "package": "mypkg"}
        doc = _normalized_doc(
            identity=identity,
            api_name="MyCustomObject__c",
            type_name="CustomObject",
            label="My Custom Object",
            description="A custom object",
            namespace="mypkg",
            organization_id=org_id,
            status="active",
            created_at=created,
            updated_at=updated,
            properties=props,
        )
        result = SearchStage._normalized_to_search_document(doc)
        assert result is not None
        assert result.id == identity
        assert result.api_name == "MyCustomObject__c"
        assert result.metadata_type == "CustomObject"
        assert result.label == "My Custom Object"
        assert result.description == "A custom object"
        assert result.namespace == "mypkg"
        assert result.organization_id == org_id
        assert result.status == "active"
        assert result.created_at == datetime.fromisoformat(created)
        assert result.updated_at == datetime.fromisoformat(updated)
        assert result.metadata_properties == props
        assert result.dependency_score == 0.0
        assert result.popularity_score == 0.0
        assert result.edge_count == 0


# ─── SearchStage.execute ────────────────────────────────────────


class TestSearchStageExecute:
    @pytest.mark.asyncio
    async def test_normal_flow(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="Contact", type_name="CustomObject"),
        ]
        context = _make_context(normalized_components=docs)
        result = await stage.execute(context)
        assert result.indexed_count == 2
        assert engine.index.total_documents == 2

    @pytest.mark.asyncio
    async def test_empty_normalized_components(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        context = _make_context(normalized_components=[])
        result = await stage.execute(context)
        assert result.indexed_count == 0
        assert engine.index.total_documents == 0

    @pytest.mark.asyncio
    async def test_none_normalized_components(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        context = _make_context(normalized_components=None)
        result = await stage.execute(context)
        assert result.indexed_count == 0

    @pytest.mark.asyncio
    async def test_single_document_indexed(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(api_name="MyTrigger", type_name="Trigger")
        search_doc = SearchStage._normalized_to_search_document(doc)
        context = _make_context(normalized_components=[doc])
        await stage.execute(context)
        assert engine.index.total_documents == 1
        retrieved = engine.index.get_document(search_doc.id)
        assert retrieved is not None
        assert retrieved.api_name == "MyTrigger"

    @pytest.mark.asyncio
    async def test_searchable_content_preserved(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(
            api_name="Account",
            type_name="CustomObject",
            label="Account Object",
            description="Standard account object",
            namespace="mypkg",
        )
        context = _make_context(normalized_components=[doc])
        await stage.execute(context)
        response = engine.search_metadata("Account")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_indexed_documents_searchable(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject", label="Account"),
            _normalized_doc(api_name="Contact", type_name="CustomObject", label="Contact"),
        ]
        context = _make_context(normalized_components=docs)
        await stage.execute(context)
        resp = engine.global_search("Contact")
        assert resp.total_count >= 1

    @pytest.mark.asyncio
    async def test_bad_data_skipped_gracefully(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        context = _make_context(
            normalized_components=[{"bad": "data"}]  # type: ignore[list-item]
        )
        result = await stage.execute(context)
        assert result.indexed_count == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_context_preserved_on_success(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [_normalized_doc(api_name="Account", type_name="CustomObject")]
        context = _make_context(normalized_components=docs)
        result = await stage.execute(context)
        assert result.organization_id == context.organization_id
        assert result.component_type == context.component_type

    @pytest.mark.asyncio
    async def test_multiple_types_indexed(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="MyClass", type_name="ApexClass"),
            _normalized_doc(api_name="MyField__c", type_name="CustomField"),
        ]
        context = _make_context(normalized_components=docs)
        await stage.execute(context)
        assert engine.index.total_documents == 3
        assert engine.index.count_by_type().get("CustomObject") == 1
        assert engine.index.count_by_type().get("ApexClass") == 1
        assert engine.index.count_by_type().get("CustomField") == 1

    @pytest.mark.asyncio
    async def test_namespace_indexed(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(
            api_name="MyClass", type_name="ApexClass", namespace="mypkg",
        )
        context = _make_context(normalized_components=[doc])
        await stage.execute(context)
        response = engine.search_metadata("", namespace="mypkg")
        assert response.total_count >= 1

    @pytest.mark.asyncio
    async def test_metadata_type_filter_works(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="MyClass", type_name="ApexClass"),
        ]
        context = _make_context(normalized_components=docs)
        await stage.execute(context)
        response = engine.search_metadata("", metadata_types=["ApexClass"])
        assert response.total_count >= 1
        for r in response.results:
            assert r.document.metadata_type == "ApexClass"


# ─── SearchEngine compatibility ─────────────────────────────────


class TestSearchEngineCompatibility:
    def test_engine_accepts_search_documents_directly(self) -> None:
        engine = SearchEngine()
        search_doc = SearchDocument(
            id="CustomObject:Account",
            api_name="Account",
            metadata_type="CustomObject",
            label="Account",
        )
        count = engine.index_components(components=[search_doc])
        assert count == 1
        assert engine.index.total_documents == 1

    @pytest.mark.asyncio
    async def test_stage_produces_search_documents(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(api_name="Account", type_name="CustomObject")
        context = _make_context(normalized_components=[doc])
        await stage.execute(context)
        search_doc = SearchStage._normalized_to_search_document(doc)
        retrieved = engine.index.get_document(search_doc.id)
        assert retrieved is not None
        assert isinstance(retrieved, SearchDocument)

    @pytest.mark.asyncio
    async def test_graph_scores_default_when_no_graph(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(api_name="Account", type_name="CustomObject")
        context = _make_context(normalized_components=[doc])
        await stage.execute(context)
        search_doc = SearchStage._normalized_to_search_document(doc)
        retrieved = engine.index.get_document(search_doc.id)
        assert retrieved is not None
        assert retrieved.dependency_score == 0.0
        assert retrieved.edge_count == 0
        assert retrieved.popularity_score == 0.0


# ─── Autocomplete compatibility ─────────────────────────────────


class TestAutocompleteCompatibility:
    @pytest.mark.asyncio
    async def test_autocomplete_from_indexed_docs(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="Account", type_name="CustomObject"),
            _normalized_doc(api_name="AccountContact", type_name="CustomObject"),
        ]
        context = _make_context(normalized_components=docs)
        await stage.execute(context)
        suggestions = engine.autocomplete("acc", limit=5)
        assert len(suggestions) >= 1


# ─── Pipeline context contract ──────────────────────────────────


class TestPipelineContextContract:
    @pytest.mark.asyncio
    async def test_context_indexed_count_matches(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        docs = [
            _normalized_doc(api_name="A", type_name="X"),
            _normalized_doc(api_name="B", type_name="X"),
            _normalized_doc(api_name="C", type_name="X"),
        ]
        context = _make_context(normalized_components=docs)
        result = await stage.execute(context)
        assert result.indexed_count == 3

    @pytest.mark.asyncio
    async def test_context_errors_empty_on_success(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        doc = _normalized_doc(api_name="A", type_name="X")
        context = _make_context(normalized_components=[doc])
        result = await stage.execute(context)
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_bad_data_does_not_cause_errors(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        context = _make_context(
            normalized_components=[{"bad": "data"}]  # type: ignore[list-item]
        )
        result = await stage.execute(context)
        assert result.indexed_count == 0
        assert len(result.errors) == 0

    @pytest.mark.asyncio
    async def test_search_stage_does_not_crash_pipeline(self) -> None:
        engine = SearchEngine()
        stage = SearchStage(engine)
        context = _make_context(normalized_components=[])
        result = await stage.execute(context)
        assert result is not None
        assert result.indexed_count == 0
        assert len(result.errors) == 0
