"""Test configuration and shared fixtures."""

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio

from sfir_backend.config.container import Container
from sfir_backend.config.settings import Settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Test settings with testing environment."""
    return Settings(
        environment="testing",
        database_url="postgresql+asyncpg://sfir:sfir@localhost:5432/sfir_test",
        database_echo=False,
    )


@pytest_asyncio.fixture
async def container(settings: Settings) -> AsyncIterator[Container]:
    """Create a DI container for testing."""
    container = Container(settings)
    await container.startup()
    yield container
    await container.shutdown()


@pytest_asyncio.fixture
async def db_session(container: Container) -> Any:
    """Create a database session for testing."""
    return container.create_session()
