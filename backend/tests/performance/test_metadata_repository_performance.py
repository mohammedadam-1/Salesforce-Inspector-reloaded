"""Performance tests for the Metadata Repository.

These tests verify query-count bounds (N+1 avoidance) using a mock
session that counts ``execute`` calls.  They do not require a database.

Run with:  pytest tests/performance/ -q -m performance
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from sfir_backend.domain.canonical.base import (
    MetadataComponent,
    MetadataStatus,
    SourcePlatform,
)
from sfir_backend.domain.repositories.metadata_repo import (
    IMetadataRepository,
    MetadataFilter,
    Pagination,
)
from sfir_backend.infrastructure.persistence.repositories.metadata_repo import (
    SQLAlchemyMetadataRepository,
    _TYPE_TO_ORM_MODEL,
)

pytestmark = pytest.mark.performance

# Types with an api_name column are queryable by name; edge tables like
# Relationship are excluded from per-name bulk lookups.
N_TYPES = sum(
    1 for m in _TYPE_TO_ORM_MODEL.values() if hasattr(m, "api_name")
)


def _make_component(
    type: str = "ApexClass",
    api_name: str = "MyClass",
    label: str = "My Class",
) -> MetadataComponent:
    return MetadataComponent(
        id=str(uuid.uuid4()),
        organization_id=str(uuid.uuid4()),
        type=type,
        api_name=api_name,
        label=label,
        description="Test",
        hash="abc",
        status=MetadataStatus.ACTIVE,
        source_platform=SourcePlatform.SALESFORCE,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_orm_instance(api_name: str) -> MagicMock:
    inst = MagicMock()
    inst.id = uuid.uuid4()
    inst.organization_id = uuid.uuid4()
    inst.api_name = api_name
    inst.label = api_name
    inst.namespace = None
    inst.description = None
    inst.fingerprint = ""
    inst.metadata_properties = {}
    inst.created_at = datetime.now(timezone.utc)
    inst.updated_at = datetime.now(timezone.utc)
    return inst


def _counting_session() -> tuple[AsyncMock, MagicMock, SQLAlchemyMetadataRepository]:
    """Return (session, counting_execute_wrapper, repo)."""
    session = AsyncMock(spec=object)
    call_count = {"n": 0}

    async def fake_execute(_query, *args, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.scalar_one_or_none.return_value = None
        result.scalar_one.return_value = 0
        return result

    session.execute = fake_execute
    repo = SQLAlchemyMetadataRepository(session)
    return session, call_count, repo


class TestBulkLoadQueryBound:
    """Bulk loading must be bounded regardless of input size."""

    @pytest.mark.parametrize("n_names", [1, 10, 100, 1000])
    async def test_get_by_api_names_query_count_bounded(
        self, n_names: int,
    ) -> None:
        _session, counter, repo = _counting_session()
        org_id = uuid.uuid4()
        api_names = [f"Class{i}" for i in range(n_names)]

        await repo.get_by_api_names(org_id, api_names)

        # At most one query per known ORM table, never one per api_name.
        assert counter["n"] <= N_TYPES
        assert counter["n"] == N_TYPES

    async def test_bulk_load_empty_is_free(self) -> None:
        _session, counter, repo = _counting_session()
        org_id = uuid.uuid4()

        await repo.get_by_api_names(org_id, [])

        assert counter["n"] == 0


class TestRelationshipsQueryBound:
    """Relationship/dependency lookups must avoid N+1."""

    @pytest.mark.parametrize("n_rels", [1, 10, 100])
    async def test_get_relationships_bounded(self, n_rels: int) -> None:
        session = AsyncMock(spec=object)
        call_count = {"n": 0}

        rels = []
        for i in range(n_rels):
            rel = MagicMock()
            rel.source_api_name = "Account"
            rel.target_api_name = f"Related{i}"
            rels.append(rel)

        async def fake_execute(query, *args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            # First call returns the relationships; later calls return components.
            if call_count["n"] == 1:
                result.scalars.return_value.all.return_value = rels
            else:
                result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = 0
            return result

        session.execute = fake_execute
        repo = SQLAlchemyMetadataRepository(session)

        await repo.get_relationships(uuid.uuid4(), "Account")

        # 1 (relationship query) + N_TYPES (batch) — independent of n_rels.
        assert call_count["n"] == 1 + N_TYPES

    @pytest.mark.parametrize("n_deps", [1, 10, 100])
    async def test_get_dependencies_bounded(self, n_deps: int) -> None:
        session = AsyncMock(spec=object)
        call_count = {"n": 0}

        deps = []
        for i in range(n_deps):
            dep = MagicMock()
            dep.source_api_name = "Account"
            dep.target_api_name = f"Dependency{i}"
            deps.append(dep)

        async def fake_execute(query, *args, **kwargs):
            call_count["n"] += 1
            result = MagicMock()
            if call_count["n"] == 1:
                result.scalars.return_value.all.return_value = deps
            else:
                result.scalars.return_value.all.return_value = []
            result.scalar_one_or_none.return_value = None
            result.scalar_one.return_value = 0
            return result

        session.execute = fake_execute
        repo = SQLAlchemyMetadataRepository(session)

        await repo.get_dependencies(uuid.uuid4(), "Account")

        assert call_count["n"] == 1 + N_TYPES


class TestSaveBatchQueryBound:
    """Batch save must flush once, not once per component."""

    @pytest.mark.parametrize("n_components", [1, 10, 100])
    async def test_save_batch_single_flush(self, n_components: int) -> None:
        session = AsyncMock(spec=object)
        session.add_all = MagicMock()
        session.flush = AsyncMock()
        repo = SQLAlchemyMetadataRepository(session)

        components = [
            _make_component("ApexClass", f"Class{i}")
            for i in range(n_components)
        ]
        await repo.save_batch(uuid.uuid4(), components)

        session.add_all.assert_called_once()
        session.flush.assert_awaited_once()


class TestGetByOrganizationQueryBound:
    """get_by_organization issues one query per requested type (bounded)."""

    async def test_all_types_bounded(self) -> None:
        _session, counter, repo = _counting_session()
        org_id = uuid.uuid4()

        await repo.get_by_organization(org_id)

        assert counter["n"] == N_TYPES

    async def test_single_type_bounded(self) -> None:
        _session, counter, repo = _counting_session()
        org_id = uuid.uuid4()

        await repo.get_by_organization(
            org_id, filter=MetadataFilter(types=["ApexClass"]),
        )

        assert counter["n"] == 1

    async def test_pagination_friendly(self) -> None:
        _session, counter, repo = _counting_session()
        org_id = uuid.uuid4()

        await repo.get_by_organization(
            org_id,
            filter=MetadataFilter(types=["ApexClass"]),
            pagination=Pagination(limit=25, offset=50),
        )

        assert counter["n"] == 1
