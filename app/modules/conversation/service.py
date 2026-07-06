"""Conversation orchestration: retrieve KB context + prior history -> generate.

This is the heart of the RAG flow. It wires together the Knowledge (retrieval),
connector (history) and agent (generation) layers but contains no transport
(HTTP) of its own. Turns are persisted to Postgres best-effort and off the
response path (never blocking the reply / stream), and only for a real
UUID-keyed tenant — the anonymous dev context is not persisted.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.config import settings
from app.modules.chatbot import service as chatbot_service
from app.modules.conversation import agent, prompts
from app.modules.conversation import intent as chat_intent
from app.modules.conversation import repository as conv_repo
from app.modules.knowledge.constants import DEFAULT_CHAT_PRODUCT
from app.modules.knowledge.rag import context_builder, retriever
from app.modules.memory import service as memory_service
from app.platform.connectors.base import ChatTurn
from app.platform.connectors import registry as connector_registry
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability.logging import get_logger
from app.platform.tenancy.chat_profile import ChatProfile, resolve_chat_profile
from app.platform.tenancy.constants import AGENT_PLATFORM_HELP
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.request_context import RequestContext

logger = get_logger(__name__)

# Small-talk / greetings: skip retrieval (no embed + no Qdrant + tiny prompt).
_SMALL_TALK = {
    "hi", "hii", "hey", "hello", "yo", "hola", "thanks", "thank you", "thx",
    "ok", "okay", "k", "cool", "great", "nice", "bye", "goodbye", "good morning",
    "good evening", "good afternoon", "how are you", "sup", "gm",
}


def _is_small_talk(message: str) -> bool:
    m = message.strip().lower().rstrip("!.?,")
    return m in _SMALL_TALK or len(m) <= 2


def _session_channel(
    tenant_ctx: TenantContext | None, profile: ChatProfile
) -> str:
    if profile.chatbot_channel:
        return profile.chatbot_channel
    if profile.agent == AGENT_PLATFORM_HELP:
        return AGENT_PLATFORM_HELP
    if isinstance(tenant_ctx, RequestContext) and tenant_ctx.channel:
        return tenant_ctx.channel
    return "web"


@dataclass
class ChatResult:
    answer: str
    sources: list[str]


async def handle(
    company_id: str,
    user_number: str,
    message: str,
    tenant_ctx: TenantContext | None = None,
    *,
    product: str | None = None,
    persist: bool = True,
    history_turns: list[ChatTurn] | None = None,
) -> ChatResult:
    """Produce a grounded answer for a user's message within a tenant context."""
    profile = await resolve_chat_profile(tenant_ctx, product=product)
    if profile.chatbot_channel:
        await chatbot_service.ensure_chatbot_enabled(tenant_ctx, profile.chatbot_channel)
    kb_context, history, memory_context, sources, procedural = await _gather_context(
        tenant_ctx,
        company_id,
        user_number,
        message,
        profile=profile,
        history_turns=history_turns,
    )
    answer = await agent.generate_answer(
        kb_context=kb_context,
        history=history,
        question=message,
        tenant_ctx=tenant_ctx,
        memory_context=memory_context,
        prompt_source=profile.prompt_source,
        chatbot_channel=profile.chatbot_channel,
        procedural=procedural,
    )
    if persist:
        _persist_async(
            tenant_ctx, user_number, message, answer, sources, profile=profile
        )
    return ChatResult(answer=answer, sources=sources)


async def _load_history_turns(
    tenant_ctx: TenantContext | None,
    company_id: str,
    user_number: str,
    *,
    history_turns: list[ChatTurn] | None,
) -> list[ChatTurn]:
    """Resolve prior turns: pushed by the product backend or pulled from connector."""
    if history_turns is not None:
        return history_turns
    connector = await connector_registry.get_connector_registry().get_conversation_connector(
        tenant_ctx, company_id
    )
    return await connector.get_conversation(
        external_user_id=user_number, company_id=company_id
    )


async def _gather_context(
    tenant_ctx: TenantContext | None,
    company_id: str,
    user_number: str,
    message: str,
    *,
    profile: ChatProfile,
    history_turns: list[ChatTurn] | None = None,
):
    """Shared step: retrieve KB chunks + prior history, build prompt blocks.

    When ``history_turns`` is provided (including an empty list), prior turns
    come from the request body — used by WhatsApp push-history. Otherwise the
    connector reads the tenant's registered data source (LMS/CRM pull model).
    """
    small_talk = _is_small_talk(message)
    procedural = chat_intent.is_procedural_query(message)
    t0 = time.perf_counter()
    if small_talk:
        chunks = []
        memory_hits = []
        resolved_history = await _load_history_turns(
            tenant_ctx, company_id, user_number, history_turns=history_turns
        )
    else:
        retrieve_k = settings.chat_procedural_top_k if procedural else None
        chunks, memory_hits, resolved_history = await asyncio.gather(
            asyncio.to_thread(
                retriever.retrieve,
                company_id,
                message,
                retrieve_k,
                kb_scope=profile.kb_scope,
                product=profile.product,
                retrieval_profile=profile.retrieval,
            ),
            asyncio.to_thread(memory_service.retrieve, company_id, message),
            _load_history_turns(
                tenant_ctx, company_id, user_number, history_turns=history_turns
            ),
        )
    kb_context = context_builder.build_kb_context(chunks, procedural=procedural)
    memory_context = context_builder.build_memory_context(memory_hits)
    history = context_builder.build_history(resolved_history)
    logger.info(
        "context: agent=%s retrieval=%s small_talk=%s procedural=%s chunks=%d memory=%d "
        "history=%d history_source=%s gather_ms=%.0f kb_chars=%d mem_chars=%d hist_chars=%d",
        profile.agent or "-",
        profile.retrieval,
        small_talk,
        procedural,
        len(chunks),
        len(memory_hits),
        len(resolved_history),
        "push" if history_turns is not None else "connector",
        (time.perf_counter() - t0) * 1000,
        len(kb_context),
        len(memory_context),
        len(history),
    )
    return kb_context, history, memory_context, context_builder.unique_sources(chunks), procedural


async def stream(
    company_id: str,
    user_number: str,
    message: str,
    tenant_ctx: TenantContext | None = None,
    *,
    product: str | None = None,
    history_turns: list[ChatTurn] | None = None,
) -> AsyncIterator[dict]:
    """Stream the answer as a sequence of events.

    Yields {"type": "token", "text": ...} for each generated piece, then a
    final {"type": "done", "sources": [...]}.
    """
    profile = await resolve_chat_profile(tenant_ctx, product=product)
    if profile.chatbot_channel:
        await chatbot_service.ensure_chatbot_enabled(tenant_ctx, profile.chatbot_channel)
    t_start = time.perf_counter()
    kb_context, history, memory_context, sources, procedural = await _gather_context(
        tenant_ctx,
        company_id,
        user_number,
        message,
        profile=profile,
        history_turns=history_turns,
    )
    approx_input_tokens = (
        len(prompts.SYSTEM_PROMPT) + len(kb_context) + len(history) + len(message)
    ) // 4
    prep_ms = (time.perf_counter() - t_start) * 1000
    logger.info("chat.stream prep_ms=%.0f approx_input_tokens=%d", prep_ms, approx_input_tokens)

    parts: list[str] = []
    ttft_ms: float | None = None
    async for token in agent.stream_answer(
        kb_context=kb_context,
        history=history,
        question=message,
        tenant_ctx=tenant_ctx,
        memory_context=memory_context,
        prompt_source=profile.prompt_source,
        chatbot_channel=profile.chatbot_channel,
        procedural=procedural,
    ):
        if ttft_ms is None:
            ttft_ms = (time.perf_counter() - t_start) * 1000
        parts.append(token)
        yield {"type": "token", "text": token}
    logger.info(
        "chat.stream done ttft_ms=%.0f total_ms=%.0f out_chars=%d",
        ttft_ms or 0.0, (time.perf_counter() - t_start) * 1000, sum(len(p) for p in parts),
    )
    yield {"type": "done", "sources": sources}
    _persist_async(
        tenant_ctx, user_number, message, "".join(parts), sources, profile=profile
    )


def _persist_async(
    tenant_ctx: TenantContext | None,
    user_number: str,
    user_message: str,
    answer: str,
    sources: list[str],
    *,
    profile: ChatProfile,
) -> None:
    """Fire-and-forget turn persistence; never blocks or raises into the caller."""
    if tenant_ctx is None or tenant_ctx.tenant_uuid() is None:
        return  # anonymous/dev: nothing to persist
    asyncio.create_task(
        _persist_turn(
            tenant_ctx, user_number, user_message, answer, sources, profile=profile
        )
    )


async def _persist_turn(
    tenant_ctx: TenantContext,
    user_number: str,
    user_message: str,
    answer: str,
    sources: list[str],
    *,
    profile: ChatProfile,
) -> None:
    tenant_id = tenant_ctx.tenant_uuid()
    if tenant_id is None:
        return
    session_channel = _session_channel(tenant_ctx, profile)
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            convo = await conv_repo.get_or_create_session(
                session, tenant_id, user_number, channel=session_channel
            )
            await conv_repo.add_message(
                session, tenant_id=tenant_id, session_id=convo.id, role="user", content=user_message
            )
            await conv_repo.add_message(
                session,
                tenant_id=tenant_id,
                session_id=convo.id,
                role="assistant",
                content=answer,
                sources=sources,
                model=settings.ollama_chat_model,
            )
            await session.commit()
            if (
                settings.memory_enabled
                and len(answer) >= settings.memory_reflect_min_answer_chars
            ):
                asyncio.create_task(
                    memory_service.reflect_turn(
                        tenant_ctx,
                        convo.id,
                        user_number,
                        user_message,
                        answer,
                        sources,
                    )
                )
    except Exception as exc:  # noqa: BLE001 - persistence must never break chat
        logger.warning("Failed to persist conversation turn: %s", exc)
