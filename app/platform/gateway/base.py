"""LLMProvider — the interface every model backend implements.

A provider is a *pure* backend adapter: given a concrete model name and messages,
produce text. It knows nothing about profiles, tenants, routing, retry, fallback
or usage tracking — those are the gateway's concerns. Adding Gemini/Claude/OpenAI
later means implementing this interface and registering it; no caller changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.platform.gateway.types import GenerationResult, Message, StreamChunk


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> GenerationResult:
        ...

    @abstractmethod
    def stream(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Return an async iterator of text chunks (implemented as an async generator)."""
