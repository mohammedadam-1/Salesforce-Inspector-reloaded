"""Unit tests for LLM provider abstractions."""

import pytest

from sfir_backend.infrastructure.llm.base import LLMPrompt, LLMResponse, ModelInfo
from sfir_backend.infrastructure.llm.factory import create_llm_provider
from sfir_backend.config.settings import get_settings


class TestLLMBaseTypes:
    def test_llm_prompt_defaults(self):
        prompt = LLMPrompt()
        assert prompt.system_prompt is None
        assert prompt.messages == []
        assert prompt.temperature == 0.1
        assert prompt.max_tokens == 4096
        assert prompt.stop_sequences is None

    def test_llm_prompt_with_values(self):
        prompt = LLMPrompt(
            system_prompt="You are a helpful assistant",
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.5,
            max_tokens=2048,
        )
        assert prompt.system_prompt == "You are a helpful assistant"
        assert len(prompt.messages) == 1
        assert prompt.temperature == 0.5

    def test_llm_response_defaults(self):
        response = LLMResponse(content="Hello", model="gpt-4o", provider="openai")
        assert response.input_tokens == 0
        assert response.output_tokens == 0
        assert response.finish_reason == "stop"

    def test_model_info_defaults(self):
        info = ModelInfo(
            name="gpt-4o",
            provider="openai",
            max_tokens=4096,
        )
        assert info.supports_streaming is True
        assert info.supports_system_prompt is True
        assert info.supports_functions is False


class TestLLMProviderFactory:
    def test_factory_raises_with_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider("nonexistent_provider")

    def test_factory_raises_without_openai_key(self):
        settings = get_settings()
        original = settings.openai_api_key
        settings.openai_api_key = None
        with pytest.raises(ValueError, match="OpenAI provider selected but"):
            create_llm_provider("openai")
