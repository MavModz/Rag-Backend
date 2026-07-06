"""OpenAI-compatible LLM provider.

One adapter for every vendor that speaks the OpenAI Chat Completions API — that
includes OpenAI itself, **NVIDIA NIM** (``https://integrate.api.nvidia.com/v1``),
Groq, Together, Fireworks, OpenRouter, vLLM, etc. Switching vendors is just a
different ``base_url`` + ``api_key`` + ``model`` (config), no code change.

The provider knows nothing about profiles/tenants/retry — those stay in the
gateway. The async client is created once; no network at construction time.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from openai import AsyncOpenAI

from app.platform.gateway.base import LLMProvider
from app.platform.gateway.types import GenerationResult, Message, StreamChunk


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, name: str = "openai", base_url: str = "", api_key: str = "") -> None:
        self.name = name
        # base_url empty -> SDK default (api.openai.com). api_key required by the SDK
        # even for some free endpoints; pass a placeholder if the vendor ignores it.
        self._client = AsyncOpenAI(base_url=base_url or None, api_key=api_key or "not-needed")

    def _payload(self, messages: list[Message]) -> list[dict]:
        return [{"role": m.role, "content": m.content} for m in messages]

    def _opts(self, temperature: float | None, max_tokens: int | None, timeout: float | None) -> dict:
        opts: dict = {}
        if temperature is not None:
            opts["temperature"] = temperature
        if max_tokens is not None:
            opts["max_tokens"] = max_tokens
        if timeout is not None:
            opts["timeout"] = timeout
        return opts

    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> GenerationResult:
        start = time.perf_counter()
        resp = await self._client.chat.completions.create(
            model=model,
            messages=self._payload(messages),
            **self._opts(temperature, max_tokens, timeout),
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        choice = resp.choices[0]
        usage = resp.usage
        return GenerationResult(
            text=choice.message.content or "",
            provider=self.name,
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            latency_ms=latency_ms,
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[StreamChunk]:
        stream = await self._client.chat.completions.create(
            model=model,
            messages=self._payload(messages),
            stream=True,
            **self._opts(temperature, max_tokens, timeout),
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield StreamChunk(text=delta)
