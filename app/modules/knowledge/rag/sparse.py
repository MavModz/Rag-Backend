"""BM25 sparse embeddings (fastembed) for hybrid retrieval.

Lexical sparse vectors complement dense (bge-m3) vectors: they catch exact terms,
IDs and rare words that dense similarity misses. Used only when
``retrieval_hybrid`` is enabled. Lazy singleton; CPU ONNX, no model server.
"""
from __future__ import annotations

from app.config import settings
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_model = None


def _get():
    global _model
    if _model is None:
        from fastembed import SparseTextEmbedding

        _model = SparseTextEmbedding(model_name=settings.sparse_model)
        logger.info("Loaded sparse model %s", settings.sparse_model)
    return _model


def embed_documents(texts: list[str]) -> list[tuple[list[int], list[float]]]:
    """(indices, values) per document, for indexing."""
    return [(list(e.indices), list(e.values)) for e in _get().embed(texts)]


def embed_query(text: str) -> tuple[list[int], list[float]]:
    """(indices, values) for a query (BM25 weights queries differently)."""
    e = next(iter(_get().query_embed(text)))
    return list(e.indices), list(e.values)
