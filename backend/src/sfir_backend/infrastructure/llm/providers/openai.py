from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    ToolDefinition,
)


class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None) -> None:
        self._model = model
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**client_kwargs)

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]
        api_tools = None
        if tools:
            api_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            tools=api_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or "",
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
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
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]
        api_tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters,
                },
            }
            for t in tools
        ]
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            tools=api_tools,
            tool_choice=tool_choice,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        return LLMResponse(
            content=choice.message.content or json.dumps(
                [t.function.arguments for t in (choice.message.tool_calls or [])],
            ),
            finish_reason=choice.finish_reason or "stop",
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
        )
