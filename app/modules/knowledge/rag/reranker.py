"""Cross-encoder reranking (fastembed ONNX).

After dense/hybrid retrieval over-fetches candidates, a cross-encoder scores each
(query, chunk) pair jointly — far more accurate than vector similarity — and we
keep the best top_k. The model is loaded lazily on first use. Defensive: if
fastembed/model is unavailable, it falls back to the retrieval order so chat
never breaks.
"""
from __future__ import annotations

from app.config import settings
from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_encoder = None  # fastembed TextCrossEncoder singleton


def _get_encoder():
    global _encoder
    if _encoder is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        _encoder = TextCrossEncoder(model_name=settings.rerank_model)
        logger.info("Loaded reranker model %s", settings.rerank_model)
    return _encoder


def rerank(query: str, chunks: list[RetrievedChunk], top_k: int) -> list[RetrievedChunk]:
    """Return the top_k chunks reordered by cross-encoder relevance."""
    if not chunks or not settings.retrieval_rerank:
        return chunks[:top_k]
    try:
        scores = list(_get_encoder().rerank(query, [c.text for c in chunks]))
        ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
        return [chunk for chunk, _ in ranked[:top_k]]
    except Exception as exc:  # noqa: BLE001 - never break retrieval on rerank failure
        logger.warning("Rerank failed (%s); using retrieval order", exc)
        return chunks[:top_k]
