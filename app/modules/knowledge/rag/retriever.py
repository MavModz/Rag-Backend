"""Retrieval: query -> candidates (dense or hybrid) -> rerank -> top-k chunks.

Pipeline: embed the query, fetch ``retrieval_candidates`` candidates (dense, or
dense+BM25 hybrid with RRF fusion), de-duplicate, then a cross-encoder reranker
scores them and we keep top_k. Each stage is timed for latency analysis.
"""
from __future__ import annotations

import time

from app.config import settings
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
from app.modules.knowledge.rag import embeddings, reranker, vector_store
from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.observability import metrics
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


def _dedupe_key(text: str) -> str:
    """Normalized key so near-identical chunks collapse to one."""
    return " ".join(text.split()).lower()[:200]


def _dedupe(raw: list[RetrievedChunk], limit: int) -> list[RetrievedChunk]:
    seen: set[str] = set()
    unique: list[RetrievedChunk] = []
    for chunk in raw:
        key = _dedupe_key(chunk.text)
        if key in seen:
            continue
        seen.add(key)
        unique.append(chunk)
        if len(unique) >= limit:
            break
    return unique


def retrieve(
    tenant_id: str,
    query: str,
    top_k: int | None = None,
    *,
    kb_scope: str = DEFAULT_KB_SCOPE,
    product: str | None = None,
    retrieval_profile: str | None = None,
) -> list[RetrievedChunk]:
    """Embed -> fetch candidates -> dedupe -> rerank -> top_k."""
    from app.platform.tenancy.constants import RETRIEVAL_PLATFORM_AND_TENANT

    profile = retrieval_profile or RETRIEVAL_PLATFORM_AND_TENANT
    if not query or not query.strip():
        return []
    k = top_k or settings.top_k
    candidates = max(settings.retrieval_candidates, k)

    t0 = time.perf_counter()
    dense = embeddings.embed_query(query)
    t_embed = time.perf_counter()

    if settings.retrieval_hybrid:
        from app.modules.knowledge.rag import sparse

        raw = vector_store.search_hybrid(
            tenant_id,
            dense,
            sparse.embed_query(query),
            candidates,
            kb_scope=kb_scope,
            product=product,
            retrieval_profile=profile,
        )
    else:
        raw = vector_store.search(
            tenant_id=tenant_id,
            query_vector=dense,
            top_k=candidates,
            kb_scope=kb_scope,
            product=product,
            retrieval_profile=profile,
        )
    t_search = time.perf_counter()

    unique = _dedupe(raw, candidates)
    final = reranker.rerank(query, unique, k)
    t_rerank = time.perf_counter()

    metrics.rag_retrieval_seconds.observe(t_search - t0)
    logger.info(
        "retrieve embed_ms=%.0f search_ms=%.0f rerank_ms=%.0f candidates=%d -> top_k=%d hybrid=%s rerank=%s kb_scope=%s product=%s retrieval=%s",
        (t_embed - t0) * 1000, (t_search - t_embed) * 1000, (t_rerank - t_search) * 1000,
        len(unique), len(final), settings.retrieval_hybrid, settings.retrieval_rerank, kb_scope,
        product or "-", profile,
    )
    return final
