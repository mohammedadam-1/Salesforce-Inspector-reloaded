"""LLM provider factory — creates the appropriate provider based on configuration."""

import structlog

from sfir_backend.config.settings import get_settings

logger = structlog.get_logger(__name__)


def create_llm_provider(provider_name: str | None = None):
    """Create an LLM provider instance based on settings.

    Args:
        provider_name: Override the default provider. If None, uses the configured default.

    Returns:
        An LLMProvider-compatible instance.

    Raises:
        ValueError: If the provider name is unknown or misconfigured.
    """
    settings = get_settings()
    provider = provider_name or settings.llm_default_provider

    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError(
                "OpenAI provider selected but SFIR_OPENAI_API_KEY is not configured"
            )
        from sfir_backend.infrastructure.llm.openai import OpenAIProvider
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.openai_api_key.get_secret_value(),
            timeout=settings.openai_timeout_seconds,
        )
        logger.info(
            "llm_provider_initialized",
            provider=provider,
            model=settings.openai_model,
        )
        return OpenAIProvider(
            client=client,
            model=settings.openai_model,
            max_tokens=settings.openai_max_tokens,
        )

    elif provider == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError(
                "Anthropic provider selected but SFIR_ANTHROPIC_API_KEY is not configured"
            )
        from sfir_backend.infrastructure.llm.anthropic import AnthropicProvider
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value(),
        )
        logger.info(
            "llm_provider_initialized",
            provider=provider,
            model=settings.anthropic_model,
        )
        return AnthropicProvider(
            client=client,
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
        )

    elif provider == "groq":
        if not settings.groq_api_key:
            raise ValueError(
                "Groq provider selected but SFIR_GROQ_API_KEY is not configured"
            )
        from sfir_backend.infrastructure.llm.groq import GroqProvider
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.groq_api_key.get_secret_value(),
            base_url="https://api.groq.com/openai/v1",
            timeout=settings.openai_timeout_seconds,
        )
        logger.info(
            "llm_provider_initialized",
            provider=provider,
            model=settings.groq_model,
        )
        return GroqProvider(
            client=client,
            model=settings.groq_model,
            max_tokens=settings.groq_max_tokens,
        )

    elif provider == "ollama":
        from sfir_backend.infrastructure.llm.ollama import OllamaProvider

        logger.info(
            "llm_provider_initialized",
            provider=provider,
            model=settings.ollama_model,
        )
        return OllamaProvider(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: openai, anthropic, groq, ollama"
        )
