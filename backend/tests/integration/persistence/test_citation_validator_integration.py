"""Integration tests for the citation validator.

Phase 10 — Validation: end-to-end ExecutionPlan -> Citation Validator
-> EvidencePackage against real PostgreSQL tables. The validator itself
is pure and in-memory — it never queries Salesforce, the search index,
the canonical store, or the graph. These tests build real plans with the
planner/retrieval engine over seeded data, then validate them, verifying
full coverage, deleted metadata, tenant isolation, and concurrency.

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
from sfir_backend.application.validator import (
    CitationValidator,
    MissingEvidence,
    MissingReason,
)
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
                email=f"validator-{uuid.uuid4().hex[:8]}@test.local",
                password_hash="x",
                display_name="Validator Test User",
            )
        )
        session.add(
            OrganizationModel(
                id=org_a,
                name="Validator Store Test Org A",
                slug=f"validator-a-{uuid.uuid4().hex[:8]}",
                description="Validator store test org A",
                owner_id=user_id,
            )
        )
        session.add(
            OrganizationModel(
                id=org_b,
                name="Validator Store Test Org B",
                slug=f"validator-b-{uuid.uuid4().hex[:8]}",
                description="Validator store test org B",
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


async def test_plan_validate_metadata_lookup_full_coverage(
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

    plan = (await Planner(make_engine()).plan(_request(org_id, "what is Account"))).plan
    package = await CitationValidator().validate(plan)

    assert [f.identity for f in package.verified_facts] == ["obj-Account"]
    assert package.required_citations == ["obj-Account"]
    assert package.coverage == 1.0
    assert package.confidence >= 0.9
    assert package.missing_evidence == []
    assert package.supporting_metadata["obj-Account"]["label"] == "Accounts"


async def test_plan_validate_impact_keeps_relationship_evidence(
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

    plan = (
        await Planner(make_engine()).plan(
            _request(org_id, "what is the impact of deleting Account")
        )
    ).plan
    package = await CitationValidator().validate(plan)

    assert [f.identity for f in package.verified_facts] == [
        "obj-Account",
        "trg-BillingProcessor",
    ]
    assert {r.identity for r in package.supporting_relationships} == {
        "obj-Account",
        "trg-BillingProcessor",
    }
    assert package.coverage == 1.0
    assert package.missing_evidence == []


async def test_deleted_metadata_reported_as_missing_evidence(
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

    plan = (await Planner(make_engine()).plan(_request(org_id, "what is Account"))).plan
    package = await CitationValidator().validate(plan)

    assert package.verified_facts == []
    assert package.coverage == 0.0
    assert package.confidence == 0.0
    assert package.missing_evidence == [
        MissingEvidence("metadata for Account", MissingReason.NOT_RETRIEVED)
    ]


async def test_tenant_isolation(db: dict[str, Any], make_engine: Any) -> None:
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

    validator = CitationValidator()
    plan_a = (await Planner(make_engine()).plan(_request(org_a, "what is Account"))).plan
    plan_b = (await Planner(make_engine()).plan(_request(org_b, "what is Account"))).plan
    package_a = await validator.validate(plan_a)
    package_b = await validator.validate(plan_b)

    assert [f.identity for f in package_a.verified_facts] == ["obj-Account"]
    assert package_a.coverage == 1.0
    assert package_a.missing_evidence == []
    assert package_b.verified_facts == []
    assert package_b.coverage == 0.0
    assert [entry.identity for entry in package_b.missing_evidence] == ["metadata for Account"]


async def test_concurrent_validation(db: dict[str, Any], make_engine: Any) -> None:
    org_id = db["org_a"]
    await _seed(
        db,
        org_id,
        [_document(org_id, "obj-Account", "object", "Account", label="Accounts")],
        [_node(org_id, "obj-Account", "object", "Account")],
        [],
    )

    validator = CitationValidator()
    planners = [Planner(make_engine()) for _ in range(5)]
    request = _request(org_id, "what is Account")
    await asyncio.gather(*(p.plan(request) for p in planners))  # warm-up
    plans = list(await asyncio.gather(*(p.plan(request) for p in planners)))
    packages = await asyncio.gather(*(validator.validate(p.plan) for p in plans))

    for package in packages:
        assert [f.identity for f in package.verified_facts] == ["obj-Account"]
        assert package.coverage == 1.0
        assert package.missing_evidence == []
