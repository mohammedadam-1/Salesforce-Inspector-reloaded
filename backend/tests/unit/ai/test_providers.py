from unittest.mock import AsyncMock

import pytest
from sfir_backend.infrastructure.llm.providers.base import LLMMessage, LLMResponse
from sfir_backend.infrastructure.llm.providers.registry import ProviderRegistry
from sfir_backend.config.settings import Settings


class TestBaseProvider:
    def test_llm_message(self) -> None:
        msg = LLMMessage(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"

    def test_llm_response(self) -> None:
        resp = LLMResponse(content="Hi there", finish_reason="stop")
        assert resp.content == "Hi there"


class TestProviderRegistry:
    def test_empty_registry_creates_noop(self) -> None:
        settings = Settings()
        from sfir_backend.infrastructure.llm.providers.registry import create_provider_registry
        registry = create_provider_registry(settings)
        providers = registry.list_providers()
        assert len(providers) >= 1

    def test_register_and_get(self) -> None:
        from sfir_backend.infrastructure.llm.providers.base import BaseLLMProvider
        from sfir_backend.infrastructure.llm.providers.openai import OpenAIProvider
        registry = ProviderRegistry(Settings())
        registry.register("test_provider", AsyncMock(spec=BaseLLMProvider))
        provider = registry.get("test_provider")
        assert provider is not None

    def test_list_providers(self) -> None:
        settings = Settings()
        from sfir_backend.infrastructure.llm.providers.registry import create_provider_registry
        registry = create_provider_registry(settings)
        providers = registry.list_providers()
        assert isinstance(providers, list)
