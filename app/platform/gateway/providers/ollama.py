"""Ollama LLM provider.

Implements ``LLMProvider`` over LangChain's ChatOllama. M1's only backend. A
ChatOllama instance is cached per (model, temperature, max_tokens) so different
profiles/models coexist without rebuilding the client each call. Token counts are
read from Ollama's response metadata (``prompt_eval_count`` / ``eval_count``).

Module-level ``generate`` / ``stream`` convenience functions are retained for the
startup prewarm; everything else goes through the gateway.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.config import settings
from app.platform.gateway.base import LLMProvider
from app.platform.gateway.types import GenerationResult, Message, StreamChunk
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


def _to_lc(messages: list[Message]):
    out = []
    for m in messages:
        if m.role == "system":
            out.append(SystemMessage(content=m.content))
        elif m.role == "assistant":
            out.append(AIMessage(content=m.content))
        else:
            out.append(HumanMessage(content=m.content))
    return out


def _extract_text(content) -> str:
    """Pull plain text out of a LangChain message/chunk content.

    Critically: a non-string, non-list content (int/None/etc.) returns "" rather
    than being stringified — that str() fallback was emitting tokens like "0".
    Handles content-block lists ([{"type":"text","text":"..."}]) from reasoning
    models too.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(block.get("text") or block.get("content") or "")
        return "".join(parts)
    return ""


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self) -> None:
        self._cache: dict[tuple, ChatOllama] = {}

    def _client(
        self, model: str, temperature: float | None, max_tokens: int | None
    ) -> ChatOllama:
        temp = settings.ollama_temperature if temperature is None else temperature
        num_predict = settings.ollama_num_predict if max_tokens is None else max_tokens
        key = (model, temp, num_predict)
        client = self._cache.get(key)
        if client is None:
            client = ChatOllama(
                model=model,
                base_url=settings.ollama_base_url,
                temperature=temp,
                keep_alive=settings.ollama_keep_alive,
                num_predict=num_predict,
                # Disable Qwen3-style "thinking" -> direct answers, lower latency.
                reasoning=settings.ollama_reasoning,
            )
            self._cache[key] = client
        return client

    async def generate(
        self,
        model: str,
        messages: list[Message],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> GenerationResult:
        client = self._client(model, temperature, max_tokens)
        start = time.perf_counter()
        response = await client.ainvoke(_to_lc(messages))
        latency_ms = int((time.perf_counter() - start) * 1000)
        meta = getattr(response, "response_metadata", {}) or {}
        prompt_tokens = int(meta.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(meta.get("eval_count", 0) or 0)
        logger.info(
            "ollama.generate model=%s prompt_tokens=%d completion_tokens=%d latency_ms=%d",
            model, prompt_tokens, completion_tokens, latency_ms,
        )
        return GenerationResult(
            text=_extract_text(response.content),
            provider=self.name,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            finish_reason=str(meta.get("done_reason", "stop")),
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
        client = self._client(model, temperature, max_tokens)
        start = time.perf_counter()
        first = True
        emitted = 0
        async for chunk in client.astream(_to_lc(messages)):
            if first:
                # Raw chunk dump — reveals exactly what Ollama/LangChain returns
                # (the source of garbage like "0"). Logged once per request.
                logger.info(
                    "ollama.stream TTFT=%.0fms model=%s first_chunk type=%s content=%r kwargs=%r",
                    (time.perf_counter() - start) * 1000, model, type(chunk).__name__,
                    getattr(chunk, "content", None), getattr(chunk, "additional_kwargs", None),
                )
                first = False
            text = _extract_text(getattr(chunk, "content", None))
            if text:
                emitted += 1
                yield StreamChunk(text=text)
        logger.info(
            "ollama.stream done model=%s emitted=%d total_ms=%.0f",
            model, emitted, (time.perf_counter() - start) * 1000,
        )


_default: OllamaProvider | None = None


def get_provider() -> OllamaProvider:
    global _default
    if _default is None:
        _default = OllamaProvider()
    return _default


async def generate(system_prompt: str, user_prompt: str) -> str:
    """Backward-compatible convenience used by the startup prewarm."""
    result = await get_provider().generate(
        settings.ollama_chat_model,
        [Message("system", system_prompt), Message("user", user_prompt)],
    )
    return result.text


async def stream(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
    async for chunk in get_provider().stream(
        settings.ollama_chat_model,
        [Message("system", system_prompt), Message("user", user_prompt)],
    ):
        yield chunk.text
