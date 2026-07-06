"""Test configuration and fixtures.

Uses test containers for PostgreSQL isolation.
For unit tests, uses in-memory SQLite or mock the database session.
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sfir_backend.config.settings import get_settings
from sfir_backend.infrastructure.database.base import Base

# Test database URL (can be overridden with env var for CI)
TEST_DATABASE_URL = "sqlite+aiosqlite:///tmp/test_sfir.db"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(engine) -> AsyncIterator[AsyncSession]:
    """Create a fresh database session for each test."""
    session_factory = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def settings():
    """Return application settings."""
    return get_settings()


@pytest.fixture
def any_uuid() -> uuid.UUID:
    """Generate a random UUID for test purposes."""
    return uuid.uuid4()


@pytest_asyncio.fixture
async def redis_mock():
    """Fixture that can be used to mock Redis.

    Override this fixture in tests that need Redis.
    """

    class MockRedis:
        _store: dict[str, Any] = {}

        async def get(self, key):
            return self._store.get(key)

        async def set(self, key, value, ex=None):
            self._store[key] = value

        async def delete(self, *keys):
            for key in keys:
                self._store.pop(key, None)

        async def ping(self):
            return True

        async def incr(self, key):
            self._store[key] = int(self._store.get(key, 0)) + 1
            return self._store[key]

        async def expire(self, key, time):
            pass

        async def zremrangebyscore(self, key, min_, max_):
            pass

        async def zcard(self, key):
            return 0

        async def zadd(self, key, mapping):
            pass

        async def scan(self, cursor=0, match=None, count=10):
            return 0, []

        async def aclose(self):
            pass

        async def aclose(self):
            pass

    return MockRedis()


@pytest.fixture
def sample_metadata_component():
    """Return a sample metadata component dict."""
    return {
        "component_type": "CustomObject",
        "api_name": "TestObject__c",
        "full_name": "TestObject__c",
        "label": "Test Object",
        "namespace_prefix": "",
        "status": "active",
    }


@pytest.fixture
def sample_salesforce_org():
    """Return a sample Salesforce org dict."""
    return {
        "name": "Test Org",
        "slug": "test-org",
        "salesforce_org_id": "00Dtest000000001",
        "instance_url": "https://test.salesforce.com",
        "environment": "sandbox",
    }
