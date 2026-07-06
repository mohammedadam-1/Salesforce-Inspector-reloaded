"""Ollama LLM provider implementation for local models."""

import time
from collections.abc import AsyncIterator

import httpx

from sfir_backend.infrastructure.llm.base import LLMPrompt, LLMProvider, LLMResponse, ModelInfo


class OllamaProvider(LLMProvider):
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.AsyncClient(timeout=120.0)

    async def generate(self, prompt: LLMPrompt) -> LLMResponse:
        start = time.monotonic()
        messages = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        messages.extend(prompt.messages)

        response = await self._client.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": prompt.temperature,
                    "num_predict": prompt.max_tokens or 4096,
                },
            },
        )
        response.raise_for_status()
        data = response.json()

        latency_ms = int((time.monotonic() - start) * 1000)

        return LLMResponse(
            content=data.get("message", {}).get("content", ""),
            model=self._model,
            provider="ollama",
            latency_ms=latency_ms,
            finish_reason="stop",
            raw=data,
        )

    async def generate_stream(
        self, prompt: LLMPrompt
    ) -> AsyncIterator[LLMResponse]:
        messages = []
        if prompt.system_prompt:
            messages.append({"role": "system", "content": prompt.system_prompt})
        messages.extend(prompt.messages)

        async with self._client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": prompt.temperature,
                    "num_predict": prompt.max_tokens or 4096,
                },
            },
        ) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                import json
                try:
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content", "")
                    if content:
                        yield LLMResponse(
                            content=content,
                            model=self._model,
                            provider="ollama",
                        )
                except json.JSONDecodeError:
                    continue

    async def get_model_info(self) -> ModelInfo:
        return ModelInfo(
            name=self._model,
            provider="ollama",
            max_tokens=4096,
            supports_streaming=True,
            supports_system_prompt=True,
            supports_functions=False,
        )

    async def count_tokens(self, text: str) -> int:
        response = await self._client.post(
            f"{self._base_url}/api/embed",
            json={"model": self._model, "input": text},
        )
        response.raise_for_status()
        data = response.json()
        return len(data.get("embeddings", [[]])[0])
