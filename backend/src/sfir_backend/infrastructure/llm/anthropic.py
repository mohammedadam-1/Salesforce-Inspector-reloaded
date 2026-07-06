"""Anthropic LLM provider implementation."""

import time
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic

from sfir_backend.infrastructure.llm.base import LLMPrompt, LLMProvider, LLMResponse, ModelInfo


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        client: AsyncAnthropic,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def generate(self, prompt: LLMPrompt) -> LLMResponse:
        start = time.monotonic()
        system = prompt.system_prompt
        messages = prompt.messages

        kwargs = dict(
            model=self._model,
            messages=messages,
            max_tokens=prompt.max_tokens or self._max_tokens,
            temperature=prompt.temperature,
        )
        if system:
            kwargs["system"] = system
        if prompt.stop_sequences:
            kwargs["stop_sequences"] = prompt.stop_sequences

        response = await self._client.messages.create(**kwargs)

        latency_ms = int((time.monotonic() - start) * 1000)
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            model=self._model,
            provider="anthropic",
            input_tokens=response.usage.input_tokens if response.usage else 0,
            output_tokens=response.usage.output_tokens if response.usage else 0,
            latency_ms=latency_ms,
            finish_reason=response.stop_reason or "stop",
            raw={},
        )

    async def generate_stream(
        self, prompt: LLMPrompt
    ) -> AsyncIterator[LLMResponse]:
        system = prompt.system_prompt
        messages = prompt.messages

        kwargs = dict(
            model=self._model,
            messages=messages,
            max_tokens=prompt.max_tokens or self._max_tokens,
            temperature=prompt.temperature,
            stream=True,
        )
        if system:
            kwargs["system"] = system

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield LLMResponse(
                    content=text,
                    model=self._model,
                    provider="anthropic",
                )

    async def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self._model,
            provider="anthropic",
            max_tokens=self._max_tokens,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_functions=False,
        )

    async def count_tokens(self, text: str) -> int:
        response = await self._client.count_tokens(text)
        return response.input_tokens
