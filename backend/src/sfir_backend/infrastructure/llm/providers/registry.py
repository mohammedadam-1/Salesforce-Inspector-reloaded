from __future__ import annotations

from typing import Any

import structlog

from sfir_backend.config.settings import Settings
from sfir_backend.domain.ai.models import AIProviderType
from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMResponse,
)

logger = structlog.get_logger(__name__)


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._providers: dict[str, BaseLLMProvider] = {}
        self._default_provider = settings.llm_default_provider

    def register(self, name: str, provider: BaseLLMProvider) -> None:
        self._providers[name] = provider
        logger.info("llm_provider_registered", name=name)

    def get(self, provider_type: str | AIProviderType | None = None) -> BaseLLMProvider:
        key = str(provider_type or self._default_provider)
        provider = self._providers.get(key)
        if provider:
            return provider
        raise ValueError(f"LLM provider not registered: {key}")

    def list_providers(self) -> list[dict[str, Any]]:
        return [
            {"name": name, "type": name}
            for name in self._providers
        ]


def create_provider_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry(settings)

    if settings.openai_api_key:
        try:
            from sfir_backend.infrastructure.llm.providers.openai import OpenAIProvider
            registry.register(
                AIProviderType.OPENAI,
                OpenAIProvider(
                    api_key=str(settings.openai_api_key),
                    model=settings.openai_model,
                ),
            )
        except Exception as e:
            logger.warning("failed_to_init_openai_provider", error=str(e))

    if settings.anthropic_api_key:
        try:
            from sfir_backend.infrastructure.llm.providers.anthropic import AnthropicProvider
            registry.register(
                AIProviderType.ANTHROPIC,
                AnthropicProvider(
                    api_key=str(settings.anthropic_api_key),
                    model=settings.anthropic_model,
                ),
            )
        except Exception as e:
            logger.warning("failed_to_init_anthropic_provider", error=str(e))

    if settings.ollama_base_url:
        try:
            from sfir_backend.infrastructure.llm.providers.ollama import OllamaProvider
            registry.register(
                AIProviderType.OLLAMA,
                OllamaProvider(
                    base_url=settings.ollama_base_url,
                    model=settings.ollama_model,
                ),
            )
        except Exception as e:
            logger.warning("failed_to_init_ollama_provider", error=str(e))

    if not registry._providers:
        class _NoopProvider(BaseLLMProvider):
            async def chat(self, _messages=None, _tools=None,
                           _temperature=0.1, _max_tokens=4096):
                return LLMResponse(content="LLM not configured. Set an API key.")

            async def chat_with_tools(self, _messages=None, _tools=None,
                                      _tool_choice="auto",
                                      _temperature=0.1, _max_tokens=4096):
                return LLMResponse(content="LLM not configured. Set an API key.")

        registry.register("default", _NoopProvider())

    return registry
