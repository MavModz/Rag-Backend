"""Embeddings via Ollama (qwen3).

Thin wrapper over LangChain's OllamaEmbeddings so the rest of the code depends
on our interface, not the library directly.
"""
from __future__ import annotations

from langchain_ollama import OllamaEmbeddings

from app.config import settings

_embedder: OllamaEmbeddings | None = None


def _get_embedder() -> OllamaEmbeddings:
    global _embedder
    if _embedder is None:
        _embedder = OllamaEmbeddings(
            model=settings.ollama_embed_model,
            base_url=settings.ollama_base_url,
            keep_alive=settings.ollama_keep_alive,
        )
    return _embedder


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed a batch of chunk texts."""
    if not texts:
        return []
    return _get_embedder().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    """Embed a single query string."""
    return _get_embedder().embed_query(text)


def reset_embedder() -> None:
    """Clear cached embedder (call after changing OLLAMA_EMBED_MODEL)."""
    global _embedder
    _embedder = None


def embedding_dimension() -> int:
    """Probe the model once to discover its vector dimension."""
    return len(embed_query("dimension probe"))
