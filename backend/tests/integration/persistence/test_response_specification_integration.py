"""Integration tests for the response specification layer.

Phase 11 — Specification: end-to-end ExecutionPlan -> EvidencePackage
-> ResponseSpecification against real PostgreSQL tables. The builder
itself is pure — it consumes only the plan and the package, never an
LLM, Salesforce, a repository, or the retrieval engine. These tests run
the full planning pipeline (planner + validator + builder) over seeded
data and verify the structural contract: answer type, sections, citation
strategy, warnings, and confidence presentation.

If the test database is unreachable the tests skip gracefully.

Marked with the ``integration`` marker (see pyproject.toml).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from sfir_backend.application.pipeline.search.search_index_builder import (
    SearchIndexBuilder,
)
from sfir_backend.application.planner import Planner, PlanningRequest
from sfir_backend.application.retrieval.retrieval_engine import RetrievalEngine
from sfir_backend.application.specification import (
    AnswerType,
    CitationStrategy,
    ConfidenceStyle,
    ResponseSpecificationBuilder,
    Section,
    SectionState,
    WarningCode,
)
from sfir_backend.application.validator import CitationValidator
from sfir_backend.config.settings import Settings
from sfir_backend.domain.entities.canonical_document import CanonicalDocument
from sfir_backend.domain.entities.canonical_relationship import (
    CanonicalRelationshipType,
)
from sfir_backend.domain.entities.graph_edge import GraphEdge
from sfir_backend.domain.entities.graph_node import GraphNode
from sfir_backend.infrastructure.persistence.models.organization import (
    OrganizationModel,
)
from sfir_backend.infrastructure.persistence.models.user import UserModel
from sfir_backend.infrastructure.persistence.repositories.canonical_repo import (
    SQLAlchemyCanonicalDocumentRepository,
)
from sfir_backend.infrastructure.persistence.repositories.graph_repo import (
    SQLAlchemyGraphRepository,
)
from sfir_backend.infrastructure.persistence.repositories.search_index_repo import (
    SQLAlchemySearchIndexRepository,
)

pytestmark = pytest.mark.integration


def _document(
    org_id: uuid.UUID,
    identity: str,
    type_name: str,
    api_name: str,
    *,
    label: str | None = None,
    description: str | None = None,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=None,
        version=1,
        previous_version=0,
        fingerprint="fp",
    )
    payload = {}
    if label:
        payload["label"] = label
    if description:
        payload["description"] = description
    if payload:
        doc.payload = payload
    return doc


def _node(
    org_id: uuid.UUID,
    identity: str,
    type_name: str,
    api_name: str,
) -> GraphNode:
    from datetime import UTC, datetime

    return GraphNode(
        id=uuid.uuid4(),
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        namespace=None,
        document_version=1,
        document_fingerprint="fp",
        version=1,
        previous_version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _edge(
    org_id: uuid.UUID,
    source_identity: str,
    source_api_name: str,
    source_type: str,
    target_identity: str,
    target_api_name: str,
    target_type: str,
    rel_type: CanonicalRelationshipType,
) -> GraphEdge:
    from datetime import UTC, datetime

    return GraphEdge(
        id=uuid.uuid4(),
        organization_id=org_id,
        source_identity=source_identity,
        source_api_name=source_api_name,
        source_type=source_type,
        target_identity=target_identity,
        target_api_name=target_api_name,
        target_type=target_type,
        relationship_type=rel_type,
        version=1,
        previous_version=0,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create the test engine, skipping if the test DB is unreachable."""
    settings = Settings(
        environment="testing",
        database_url="postgresql+asyncpg://sfir:sfir@localhost:5432/sfir_test",
    )
    engine = create_async_engine(
        settings.database_url.get_secret_value(),
        echo=False,
        pool_pre_ping=True,
    )
    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - depends on environment
        await engine.dispose()
        pytest.skip(f"Test database unavailable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(engine: AsyncEngine, session_factory: Any) -> AsyncIterator[dict[str, Any]]:
    """Create tables, seed two organizations, and clean up."""
    from sfir_backend.infrastructure.database.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    org_a = uuid.uuid4()
    org_b = uuid.uuid4()
    user_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            UserModel(
                id=user_id,
                email=f"spec-{uuid.uuid4().hex[:8]}@test.local",
                password_hash="x",
                display_name="Spec Test User",
            )
        )
        session.add(
            OrganizationModel(
                id=org_a,
                name="Spec Store Test Org A",
                slug=f"spec-a-{uuid.uuid4().hex[:8]}",
                description="Spec store test org A",
                owner_id=user_id,
            )
        )
        session.add(
            OrganizationModel(
                id=org_b,
                name="Spec Store Test Org B",
                slug=f"spec-b-{uuid.uuid4().hex[:8]}",
                description="Spec store test org B",
                owner_id=user_id,
            )
        )
        await session.commit()

    yield {
        "org_a": org_a,
        "org_b": org_b,
        "session_factory": session_factory,
    }

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def _seed(
    db: dict[str, Any],
    org_id: uuid.UUID,
    docs: list[CanonicalDocument],
    nodes: list[GraphNode],
    edges: list[GraphEdge],
) -> None:
    """Persist canonical docs, graph nodes/edges, and the search index."""
    session_factory = db["session_factory"]
    async with session_factory() as session:
        await SQLAlchemyCanonicalDocumentRepository(session).upsert_batch(
            org_id,
            docs,
        )
        await SQLAlchemyGraphRepository(session).upsert_nodes(org_id, nodes)
        await SQLAlchemyGraphRepository(session).upsert_edges(org_id, edges)
    async with session_factory() as session:
        await SearchIndexBuilder().build(
            org_id,
            docs,
            nodes,
            edges,
            SQLAlchemySearchIndexRepository(session),
        )


@pytest_asyncio.fixture
async def make_engine(db: dict[str, Any]) -> AsyncIterator[Any]:
    sessions: list[AsyncSession] = []

    def _make() -> RetrievalEngine:
        session = db["session_factory"]()
        sessions.append(session)
        return RetrievalEngine(
            search_repo=SQLAlchemySearchIndexRepository(session),
            canonical_repo=SQLAlchemyCanonicalDocumentRepository(session),
            graph_repo=SQLAlchemyGraphRepository(session),
        )

    yield _make
    for session in sessions:
        await session.close()


def _request(org_id: uuid.UUID, question: str) -> PlanningRequest:
    return PlanningRequest(
        organization_id=org_id,
        question=question,
        source_timeout_ms=2000.0,
        total_timeout_ms=5000.0,
    )


async def _specify(
    make_engine: Any,
    request: PlanningRequest,
    validator: CitationValidator,
    builder: ResponseSpecificationBuilder,
) -> Any:
    plan = (await Planner(make_engine()).plan(request)).plan
    package = await validator.validate(plan)
    return await builder.build(plan, package)


async def test_spec_metadata_lookup_end_to_end(
    db: dict[str, Any],
    make_engine: Any,
) -> None:
    org_id = db["org_a"]
    await _seed(
        db,
        org_id,
        [_document(org_id, "obj-Account", "object", "Account", label="Accounts")],
        [_node(org_id, "obj-Account", "object", "Account")],
        [],
    )

    spec = await _specify(
        make_engine,
        _request(org_id, "what is Account"),
        CitationValidator(),
        ResponseSpecificationBuilder(),
    )

    assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
    assert [(s.section, s.state) for s in spec.sections] == [
        (Section.SUMMARY, SectionState.REQUIRED),
        (Section.METADATA_DETAILS, SectionState.REQUIRED),
        (Section.CITATIONS, SectionState.REQUIRED),
        (Section.WARNINGS, SectionState.OPTIONAL),
    ]
    assert spec.evidence_ordering == ["obj-Account"]
    assert spec.citation_strategy is CitationStrategy.FOOTNOTE
    assert spec.warnings == []
    assert spec.confidence_display.style is ConfidenceStyle.PERCENTAGE


async def test_spec_impact_analysis_with_neighbors(
    db: dict[str, Any],
    make_engine: Any,
) -> None:
    org_id = db["org_a"]
    docs = [
        _document(org_id, "obj-Account", "object", "Account", label="Accounts"),
        _document(org_id, "trg-BillingProcessor", "trigger", "BillingProcessor"),
    ]
    nodes = [
        _node(org_id, "obj-Account", "object", "Account"),
        _node(org_id, "trg-BillingProcessor", "trigger", "BillingProcessor"),
    ]
    edges = [
        _edge(
            org_id,
            "obj-Account",
            "Account",
            "object",
            "trg-BillingProcessor",
            "BillingProcessor",
            "trigger",
            CanonicalRelationshipType.TRIGGER_TO_OBJECT,
        ),
    ]
    await _seed(db, org_id, docs, nodes, edges)

    spec = await _specify(
        make_engine,
        _request(org_id, "what is the impact of deleting Account"),
        CitationValidator(),
        ResponseSpecificationBuilder(),
    )

    assert spec.answer_type is AnswerType.IMPACT_SUMMARY
    assert spec.citation_strategy is CitationStrategy.GROUPED_BY_SECTION
    impact = [s for s in spec.sections if s.section is Section.IMPACT_LIST]
    assert impact[0].state is SectionState.REQUIRED
    assert spec.evidence_ordering[0] == "obj-Account"
    assert spec.warnings == []


async def test_spec_deleted_metadata_becomes_no_answer(
    db: dict[str, Any],
    make_engine: Any,
) -> None:
    org_id = db["org_a"]
    await _seed(
        db,
        org_id,
        [_document(org_id, "obj-Account", "object", "Account", label="Accounts")],
        [_node(org_id, "obj-Account", "object", "Account")],
        [],
    )
    async with db["session_factory"]() as session:
        await SQLAlchemyCanonicalDocumentRepository(session).soft_delete_by_identity(
            org_id,
            "obj-Account",
        )

    spec = await _specify(
        make_engine,
        _request(org_id, "what is Account"),
        CitationValidator(),
        ResponseSpecificationBuilder(),
    )

    assert spec.answer_type is AnswerType.NO_ANSWER
    assert WarningCode.NO_EVIDENCE in spec.warnings
    assert WarningCode.EVIDENCE_INCOMPLETE in spec.warnings
    assert spec.citation_strategy is CitationStrategy.NONE
    assert spec.confidence_display.style is ConfidenceStyle.HIDDEN


async def test_spec_tenant_isolation(db: dict[str, Any], make_engine: Any) -> None:
    org_a = db["org_a"]
    org_b = db["org_b"]
    await _seed(
        db,
        org_a,
        [_document(org_a, "obj-Account", "object", "Account")],
        [_node(org_a, "obj-Account", "object", "Account")],
        [],
    )
    await _seed(
        db,
        org_b,
        [_document(org_b, "obj-Contact", "object", "Contact")],
        [_node(org_b, "obj-Contact", "object", "Contact")],
        [],
    )

    spec_a = await _specify(
        make_engine,
        _request(org_a, "what is Account"),
        CitationValidator(),
        ResponseSpecificationBuilder(),
    )
    spec_b = await _specify(
        make_engine,
        _request(org_b, "what is Account"),
        CitationValidator(),
        ResponseSpecificationBuilder(),
    )

    assert spec_a.organization_id == org_a
    assert spec_a.answer_type is AnswerType.METADATA_DESCRIPTION
    assert spec_a.evidence_ordering == ["obj-Account"]
    assert spec_b.organization_id == org_b
    assert spec_b.answer_type is AnswerType.NO_ANSWER


async def test_spec_concurrent_pipelines(db: dict[str, Any], make_engine: Any) -> None:
    org_id = db["org_a"]
    await _seed(
        db,
        org_id,
        [_document(org_id, "obj-Account", "object", "Account", label="Accounts")],
        [_node(org_id, "obj-Account", "object", "Account")],
        [],
    )

    validator = CitationValidator()
    builder = ResponseSpecificationBuilder()
    planners = [Planner(make_engine()) for _ in range(5)]
    request = _request(org_id, "what is Account")
    await asyncio.gather(*(p.plan(request) for p in planners))  # warm-up
    plans = list(await asyncio.gather(*(p.plan(request) for p in planners)))
    packages = await asyncio.gather(*(validator.validate(p.plan) for p in plans))
    specs = await asyncio.gather(
        *(builder.build(p.plan, package) for p, package in zip(plans, packages, strict=True))
    )

    for spec in specs:
        assert spec.answer_type is AnswerType.METADATA_DESCRIPTION
        assert spec.evidence_ordering == ["obj-Account"]
        assert spec.warnings == []
        assert spec.confidence_display.style is ConfidenceStyle.PERCENTAGE
