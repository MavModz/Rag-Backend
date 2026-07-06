"""Qdrant store for tenant-scoped memory vectors (dense only)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from qdrant_client.http import models as qmodels

from app.config import settings
from app.modules.knowledge.rag import embeddings
from app.modules.knowledge.rag.vector_store import _is_local, _tenant_match, get_qdrant_client
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryHit:
    summary: str
    memory_type: str
    score: float
    source_question: str | None = None


def ensure_collection() -> None:
    client = get_qdrant_client()
    name = settings.qdrant_memory_collection
    if client.collection_exists(name):
        existing = client.get_collection(name)
        vectors = existing.config.params.vectors
        existing_dim = vectors.size if not isinstance(vectors, dict) else vectors["dense"].size
        current_dim = embeddings.embedding_dimension()
        if existing_dim != current_dim:
            raise RuntimeError(
                f"Memory collection '{name}' dimension mismatch ({existing_dim} vs {current_dim}). "
                "Drop it manually or use reset_vectors if you changed the embedding model."
            )
        return
    dim = embeddings.embedding_dimension()
    client.create_collection(
        collection_name=name,
        vectors_config=qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE),
    )
    if not _is_local():
        for field in ("tenant_id", "company_id", "memory_type"):
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )
    logger.info("Created Qdrant memory collection '%s' (dim=%d)", name, dim)


def upsert(
    tenant_id: str,
    summary: str,
    vector: list[float],
    *,
    memory_type: str,
    source_question: str | None = None,
    vector_id: str | None = None,
) -> str:
    ensure_collection()
    client = get_qdrant_client()
    point_id = vector_id or str(uuid.uuid4())
    payload: dict = {
        "tenant_id": tenant_id,
        "memory_type": memory_type,
        "text": summary,
    }
    if source_question:
        payload["source_question"] = source_question
    client.upsert(
        collection_name=settings.qdrant_memory_collection,
        points=[
            qmodels.PointStruct(id=point_id, vector=vector, payload=payload),
        ],
    )
    return point_id


def search(tenant_id: str, query_vector: list[float], top_k: int) -> list[MemoryHit]:
    if not settings.memory_enabled:
        return []
    ensure_collection()
    client = get_qdrant_client()
    tenant_filter = qmodels.Filter(should=_tenant_match(tenant_id))
    hits = client.query_points(
        collection_name=settings.qdrant_memory_collection,
        query=query_vector,
        query_filter=tenant_filter,
        limit=top_k,
        with_payload=True,
    ).points
    results: list[MemoryHit] = []
    for hit in hits:
        if hit.score is None or hit.score < settings.memory_min_score:
            continue
        payload = hit.payload or {}
        results.append(
            MemoryHit(
                summary=payload.get("text", ""),
                memory_type=payload.get("memory_type", "insight"),
                score=hit.score,
                source_question=payload.get("source_question"),
            )
        )
    return results
