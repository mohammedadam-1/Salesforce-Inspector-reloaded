from __future__ import annotations

from typing import Any, AsyncIterator

import google.genai as genai
from google.genai import types

from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolDefinition,
)


class GeminiProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)

    def _to_google_content(self, messages: list[LLMMessage]) -> list[types.Content]:
        result = []
        for m in messages:
            if m.role == "system":
                continue
            role = "model" if m.role == "assistant" else "user"
            result.append(types.Content(role=role, parts=[types.Part.from_text(text=m.content)]))
        return result

    def _system_instruction(self, messages: list[LLMMessage]) -> str | None:
        for m in messages:
            if m.role == "system":
                return m.content
        return None

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        google_messages = self._to_google_content(messages)
        sys_instruction = self._system_instruction(messages)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=sys_instruction,
        )
        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=google_messages,
            config=config,
        )
        text = response.text or ""
        usage = response.usage_metadata
        return LLMResponse(
            content=text,
            finish_reason="stop",
            usage={
                "prompt_tokens": usage.prompt_token_count if usage else 0,
                "completion_tokens": usage.candidates_token_count if usage else 0,
                "total_tokens": (usage.prompt_token_count + usage.candidates_token_count) if usage else 0,
            },
        )

    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        return await self.chat(
            messages=messages,
            tools=tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMStreamChunk]:
        google_messages = self._to_google_content(messages)
        sys_instruction = self._system_instruction(messages)
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            system_instruction=sys_instruction,
        )
        async for chunk in await self._client.aio.models.generate_content_stream(
            model=self._model,
            contents=google_messages,
            config=config,
        ):
            if chunk.text:
                yield LLMStreamChunk(content=chunk.text)

        yield LLMStreamChunk(content="", done=True)
