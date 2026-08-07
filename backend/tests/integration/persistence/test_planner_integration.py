"""Integration tests for the AI planner.

Phase 9 — Planning: the planner detects intent, builds retrieval
requests, and produces execution plans end-to-end against real
PostgreSQL tables seeded through the canonical/graph/search-index
repositories. These tests verify the planner's evidence rules, retry
behaviour, tenant isolation, and concurrency safety — never answers.

The planner itself never queries the stores directly; only the
RetrievalEngine it owns does. If the test database is unreachable the
tests skip gracefully.

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
from sfir_backend.application.planner import (
    AnswerStrategy,
    Planner,
    PlanningRequest,
)
from sfir_backend.application.retrieval.retrieval_engine import RetrievalEngine
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
    namespace: str | None = None,
) -> CanonicalDocument:
    doc = CanonicalDocument.create(
        organization_id=org_id,
        identity=identity,
        type=type_name,
        api_name=api_name,
        developer_name=api_name,
        namespace=namespace,
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
                email=f"planner-{uuid.uuid4().hex[:8]}@test.local",
                password_hash="x",
                display_name="Planner Test User",
            )
        )
        session.add(
            OrganizationModel(
                id=org_a,
                name="Planner Store Test Org A",
                slug=f"planner-a-{uuid.uuid4().hex[:8]}",
                description="Planner store test org A",
                owner_id=user_id,
            )
        )
        session.add(
            OrganizationModel(
                id=org_b,
                name="Planner Store Test Org B",
                slug=f"planner-b-{uuid.uuid4().hex[:8]}",
                description="Planner store test org B",
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


def _generous(**overrides: float) -> dict[str, float]:
    return {"source_timeout_ms": 2000.0, "total_timeout_ms": 5000.0, **overrides}


async def test_planner_metadata_lookup_end_to_end(
    db: dict[str, Any],
    make_engine: Any,
) -> None:
    org_id = db["org_a"]
    docs = [
        _document(
            org_id,
            "obj-Account",
            "object",
            "Account",
            label="Accounts",
            description="Customers",
        ),
    ]
    await _seed(db, org_id, docs, [_node(org_id, "obj-Account", "object", "Account")], [])


    result = await Planner(make_engine()).plan(
        PlanningRequest(organization_id=org_id, question="what is Account", **_generous())
    )

    plan = result.plan
    assert plan.intent == "metadata_lookup"
    assert plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA
    assert plan.required_citations == ["obj-Account"]
    assert plan.missing_facts == []
    assert plan.retry_count == 0
    assert plan.confidence >= 0.9
    fact = plan.retrieved_facts[0]
    assert fact.display_name == "Accounts"
    assert fact.description == "Customers"
    assert fact.supporting_metadata["label"] == "Accounts"
    assert result.requests_made[0].query == "Account"


async def test_planner_impact_analysis_surfaces_neighbors(
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


    result = await Planner(make_engine()).plan(
        PlanningRequest(
            organization_id=org_id,
            question="what is the impact of deleting Account",
            **_generous(),
        )
    )

    plan = result.plan
    assert plan.intent == "impact_analysis"
    assert plan.answer_strategy == AnswerStrategy.IMPACT_SUMMARY
    assert plan.required_citations == ["obj-Account", "trg-BillingProcessor"]
    assert plan.missing_facts == []
    relationships = {
        r.identity for r in plan.retrieved_facts[0].supporting_relationships
    }
    assert "trg-BillingProcessor" in relationships
    assert plan.confidence >= 0.8


async def test_planner_retries_then_reports_missing_evidence(
    db: dict[str, Any],
    make_engine: Any,
) -> None:
    org_id = db["org_a"]
    await _seed(db, org_id, [], [], [])


    result = await Planner(make_engine()).plan(
        PlanningRequest(organization_id=org_id, question="what is Account", **_generous())
    )

    assert len(result.requests_made) == 2
    assert result.requests_made[0].mode == "exact"
    assert result.requests_made[1].mode == "fuzzy"
    assert result.plan.retry_count == 1
    assert result.plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert result.plan.required_citations == []
    assert result.plan.missing_facts == ["metadata for Account"]
    assert result.plan.confidence < 0.7


async def test_planner_tenant_isolation(db: dict[str, Any], make_engine: Any) -> None:
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


    planner = Planner(make_engine())
    result_a = await planner.plan(
        PlanningRequest(organization_id=org_a, question="what is Account", **_generous())
    )
    result_b = await planner.plan(
        PlanningRequest(organization_id=org_b, question="what is Account", **_generous())
    )

    assert result_a.plan.required_citations == ["obj-Account"]
    assert result_a.plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA
    assert result_b.plan.required_citations == []
    assert result_b.plan.answer_strategy == AnswerStrategy.NEEDS_MORE_INFO
    assert result_b.plan.organization_id == org_b


async def test_planner_concurrent_planning(db: dict[str, Any], make_engine: Any) -> None:
    org_id = db["org_a"]
    docs = [_document(org_id, f"obj-O{i}", "object", f"O{i}") for i in range(10)]
    nodes = [_node(org_id, f"obj-O{i}", "object", f"O{i}") for i in range(10)]
    await _seed(db, org_id, docs, nodes, [])


    planners = [Planner(make_engine()) for _ in range(5)]
    request = PlanningRequest(
        organization_id=org_id,
        question="what is O1",
        **_generous(),
    )
    await asyncio.gather(*(p.plan(request) for p in planners))  # warm-up
    results = await asyncio.gather(*(p.plan(request) for p in planners))

    for result in results:
        assert result.plan.answer_strategy == AnswerStrategy.DESCRIBE_METADATA
        assert result.plan.required_citations == ["obj-O1"]
        assert result.plan.retry_count == 0
        # Planning latency mirrors retrieval latency; allow slack for the
        # emulated WSL -> socat -> Docker environment.
        assert result.elapsed_ms < 1000
