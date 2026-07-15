from __future__ import annotations

from typing import Any, AsyncIterator

import httpx

from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolDefinition,
)


class OllamaProvider(BaseLLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

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
        body: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json=body,
        )
        response.raise_for_status()
        result = response.json()
        return LLMResponse(
            content=result.get("message", {}).get("content", ""),
            finish_reason="stop",
            usage={
                "prompt_tokens": result.get("prompt_eval_count", 0),
                "completion_tokens": result.get("eval_count", 0),
                "total_tokens": result.get("prompt_eval_count", 0) + result.get("eval_count", 0),
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
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def chat_stream(
        self,
        messages: list[LLMMessage],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncIterator[LLMStreamChunk]:
        api_messages = [
            {"role": m.role, "content": m.content}
            for m in messages
        ]
        body: dict[str, Any] = {
            "model": self._model,
            "messages": api_messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        async with self._client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                import json as json_mod
                try:
                    chunk = json_mod.loads(line)
                except json_mod.JSONDecodeError:
                    continue
                if chunk.get("done"):
                    yield LLMStreamChunk(
                        content="",
                        done=True,
                        finish_reason="stop",
                        usage={
                            "prompt_tokens": chunk.get("prompt_eval_count", 0),
                            "completion_tokens": chunk.get("eval_count", 0),
                            "total_tokens": chunk.get("prompt_eval_count", 0) + chunk.get("eval_count", 0),
                        },
                    )
                else:
                    yield LLMStreamChunk(content=chunk.get("message", {}).get("content", ""))
