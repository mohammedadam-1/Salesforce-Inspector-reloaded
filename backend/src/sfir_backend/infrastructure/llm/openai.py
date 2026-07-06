"""OpenAI LLM provider implementation."""

import time
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI

from sfir_backend.infrastructure.llm.base import LLMPrompt, LLMProvider, LLMResponse, ModelInfo


class OpenAIProvider(LLMProvider):
    def __init__(
        self,
        client: AsyncOpenAI,
        model: str = "gpt-4o",
        max_tokens: int = 4096,
    ) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    async def generate(self, prompt: LLMPrompt) -> LLMResponse:
        start = time.monotonic()
        messages = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        messages.extend(prompt.messages)

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens or self._max_tokens,
            stop=prompt.stop_sequences,
        )

        latency_ms = int((time.monotonic() - start) * 1000)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            model=self._model,
            provider="openai",
            input_tokens=response.usage.prompt_tokens if response.usage else 0,
            output_tokens=response.usage.completion_tokens if response.usage else 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
            raw=response.model_dump() if hasattr(response, "model_dump") else {},
        )

    async def generate_stream(
        self, prompt: LLMPrompt
    ) -> AsyncIterator[LLMResponse]:
        messages = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        messages.extend(prompt.messages)

        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=prompt.temperature,
            max_tokens=prompt.max_tokens or self._max_tokens,
            stop=prompt.stop_sequences,
            stream=True,
        )

        full_content = ""
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                full_content += delta.content
                yield LLMResponse(
                    content=delta.content,
                    model=self._model,
                    provider="openai",
                )

    async def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self._model,
            provider="openai",
            max_tokens=self._max_tokens,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_functions=True,
        )

    async def count_tokens(self, text: str) -> int:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "user", "content": text}],
            max_tokens=1,
        )
        return response.usage.prompt_tokens if response.usage else 0
