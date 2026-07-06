"""Abstract LLM provider interface.

All LLM providers must implement this interface to be swappable.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = "stop"
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMPrompt:
    system_prompt: str | None = None
    messages: list[dict[str, str]] = field(default_factory=list)
    temperature: float = 0.1
    max_tokens: int = 4096
    stop_sequences: list[str] | None = None


@dataclass
class ModelInfo:
    name: str
    provider: str
    max_tokens: int
    supports_streaming: bool = True
    supports_system_prompt: bool = True
    supports_functions: bool = False


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: LLMPrompt) -> LLMResponse:
        """Generate a response from the LLM."""
        ...

    @abstractmethod
    async def generate_stream(
        self, prompt: LLMPrompt
    ) -> AsyncIterator[LLMResponse]:
        """Stream a response from the LLM."""
        ...
        yield  # pragma: no cover

    @abstractmethod
    async def get_model_info(self) -> ModelInfo:
        """Get information about the current model."""
        ...

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Count tokens in a text string."""
        ...
