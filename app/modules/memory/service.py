"""Memory service: retrieve past learnings and reflect on new chat turns."""
from __future__ import annotations

import uuid

from app.config import settings
from app.modules.knowledge.rag import embeddings
from app.modules.memory import prompts, repository, vector_store
from app.modules.memory.models import MEMORY_TYPE_INSIGHT, MEMORY_TYPE_VERIFIED_QA
from app.modules.memory.vector_store import MemoryHit
from app.platform.db.postgres import get_sessionmaker
from app.platform.gateway.gateway import get_gateway
from app.platform.gateway.types import Message
from app.platform.observability.logging import get_logger
from app.platform.tenancy.context import TenantContext

logger = get_logger(__name__)

_SUMMARIZE_PROFILE = "memory.summarize"
_NONE_MARKERS = frozenset({"none", "none.", "n/a"})


def retrieve(tenant_id: str, query: str) -> list[MemoryHit]:
    """Return tenant-scoped memory hits relevant to the user's question."""
    if not settings.memory_enabled or not query.strip():
        return []
    try:
        vector = embeddings.embed_query(query)
        return vector_store.search(tenant_id, vector, settings.memory_top_k)
    except Exception as exc:  # noqa: BLE001 - memory must not break chat
        logger.warning("Memory retrieve failed: %s", exc)
        return []


async def reflect_turn(
    tenant_ctx: TenantContext,
    session_id: uuid.UUID,
    external_user_id: str,
    question: str,
    answer: str,
    sources: list[str],
) -> None:
    """Summarize a substantive Q+A pair and store as tenant memory (best-effort)."""
    if not settings.memory_enabled:
        return
    tenant_id = tenant_ctx.tenant_uuid()
    if tenant_id is None:
        return
    try:
        prompt = prompts.build_reflect_prompt(question, answer, sources)
        result = await get_gateway().generate(
            _SUMMARIZE_PROFILE,
            [Message("user", prompt)],
            tenant_ctx=tenant_ctx,
        )
        insight = result.text.strip()
        if not insight or insight.lower() in _NONE_MARKERS:
            return
        tenant_key = str(tenant_id)
        vector = embeddings.embed_query(insight)
        vector_id = vector_store.upsert(
            tenant_key,
            insight,
            vector,
            memory_type=MEMORY_TYPE_INSIGHT,
            source_question=question,
        )
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await repository.create_memory(
                session,
                tenant_id=tenant_id,
                session_id=session_id,
                external_user_id=external_user_id,
                memory_type=MEMORY_TYPE_INSIGHT,
                summary=insight,
                source_question=question,
                vector_id=vector_id,
            )
            await session.commit()
        logger.info("Stored memory insight for tenant=%s (chars=%d)", tenant_key, len(insight))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Memory reflect failed: %s", exc)


async def store_verified_qa(
    tenant_ctx: TenantContext,
    question: str,
    answer: str,
    *,
    external_user_id: str | None = None,
) -> None:
    """Promote a Q+A pair to verified memory without LLM summarization."""
    if not settings.memory_enabled:
        return
    tenant_id = tenant_ctx.tenant_uuid()
    if tenant_id is None:
        return
    summary = f"Q: {question.strip()}\nA: {answer.strip()}"
    tenant_key = str(tenant_id)
    try:
        vector = embeddings.embed_query(question)
        vector_id = vector_store.upsert(
            tenant_key,
            summary,
            vector,
            memory_type=MEMORY_TYPE_VERIFIED_QA,
            source_question=question,
        )
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            await repository.create_memory(
                session,
                tenant_id=tenant_id,
                external_user_id=external_user_id,
                memory_type=MEMORY_TYPE_VERIFIED_QA,
                summary=summary,
                source_question=question,
                vector_id=vector_id,
            )
            await session.commit()
        logger.info("Stored verified Q&A memory for tenant=%s", tenant_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Verified Q&A memory store failed: %s", exc)
