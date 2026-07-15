"""Tests for the dependency injection container."""

import pytest

from sfir_backend.config.container import Container
from sfir_backend.config.settings import Settings


class TestContainer:
    """Verify the DI container bootstraps correctly."""

    @pytest.mark.asyncio
    async def test_container_startup_shutdown(self) -> None:
        """Container should start and shut down without errors."""
        settings = Settings(environment="testing")
        container = Container(settings)
        assert container._initialized is False

        await container.startup()
        assert container._initialized is True

        await container.shutdown()
        assert container._initialized is False

    @pytest.mark.asyncio
    async def test_container_ports_available(self) -> None:
        """Core ports should be registered after startup."""
        settings = Settings(environment="testing")
        container = Container(settings)
        await container.startup()

        cache = container.get_port("cache")
        assert cache is not None

        clock = container.get_port("clock")
        assert clock is not None

        await container.shutdown()

    def test_container_unregistered_port_raises(self) -> None:
        """Accessing an unregistered port should raise KeyError."""
        settings = Settings(environment="testing")
        container = Container(settings)

        with pytest.raises(KeyError, match="Port not registered"):
            container.get_port("nonexistent")
