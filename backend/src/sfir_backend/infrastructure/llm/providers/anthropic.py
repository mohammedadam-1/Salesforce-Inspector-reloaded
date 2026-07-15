from __future__ import annotations

from typing import Any, AsyncIterator

from anthropic import AsyncAnthropic

from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolDefinition,
)


class AnthropicProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        system_msg = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        response = await self._client.messages.create(**kwargs)
        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        return LLMResponse(
            content=content,
            finish_reason=response.stop_reason or "stop",
            usage={
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
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
        system_msg = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if system_msg:
            kwargs["system"] = system_msg

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield LLMStreamChunk(content=text)

            final = await stream.get_final_message()
            yield LLMStreamChunk(
                content="",
                done=True,
                finish_reason=final.stop_reason or "stop",
                usage={
                    "prompt_tokens": final.usage.input_tokens,
                    "completion_tokens": final.usage.output_tokens,
                    "total_tokens": final.usage.input_tokens + final.usage.output_tokens,
                },
            )
