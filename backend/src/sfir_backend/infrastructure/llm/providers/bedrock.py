from __future__ import annotations

import json
from typing import Any, AsyncIterator

from sfir_backend.infrastructure.llm.providers.base import (
    BaseLLMProvider,
    LLMMessage,
    LLMResponse,
    LLMStreamChunk,
    ToolDefinition,
)


class BedrockProvider(BaseLLMProvider):
    def __init__(
        self,
        model: str = "anthropic.claude-sonnet-4-20250514",
        region: str = "us-east-1",
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
    ) -> None:
        self._model = model
        self._region = region
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        import aioboto3
        session = aioboto3.Session(
            aws_access_key_id=self._access_key_id,
            aws_secret_access_key=self._secret_access_key,
            region_name=self._region,
        )
        self._client = session.client("bedrock-runtime")
        return self._client

    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        client = await self._get_client()
        system_msg = None
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg = m.content
            else:
                api_messages.append({"role": m.role, "content": [{"text": m.content}]})

        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_msg:
            body["system"] = system_msg

        response = await client.invoke_model(
            modelId=self._model,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(body),
        )
        result = json.loads(await response["body"].read())
        content = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                content += block["text"]

        usage = result.get("usage", {})
        return LLMResponse(
            content=content,
            finish_reason=result.get("stop_reason", "stop"),
            usage={
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
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
        response = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield LLMStreamChunk(
            content=response.content,
            done=True,
            finish_reason=response.finish_reason,
            usage=response.usage,
        )
