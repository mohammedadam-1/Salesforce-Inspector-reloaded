from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMMessage:
    role: str
    content: str
    name: str | None = None


@dataclass
class LLMResponse:
    content: str
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class LLMStreamChunk:
    content: str
    done: bool = False
    finish_reason: str | None = None
    usage: dict[str, int] | None = None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

    @abstractmethod
    async def chat_with_tools(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition],
        tool_choice: str = "auto",
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        ...

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
