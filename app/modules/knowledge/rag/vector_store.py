"""Qdrant vector store.

Single collection holds all tenants' chunks; every point carries a `company_id`
in its payload and all searches filter on it, so a tenant's bot only ever
retrieves its own documents (multi-tenant isolation). Phase 6 generalizes the
payload key from `company_id` to `tenant_id` with a dual-read compatibility
window.

Local (on-disk) mode is single-process — fine for the dev server. For production
set QDRANT_URL to a Qdrant server; the client constructor switches automatically.
"""
from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings
from app.modules.knowledge.constants import (
    DEFAULT_KB_SCOPE,
    DOC_SCOPE_PLATFORM,
    DOC_SCOPE_TENANT,
)
from app.modules.knowledge.rag import embeddings
from app.platform.tenancy.constants import (
    KNOWN_PRODUCTS,
    PRODUCT_LMS,
    RETRIEVAL_PLATFORM_AND_TENANT,
    RETRIEVAL_PLATFORM_ONLY,
    RETRIEVAL_TENANT_ONLY,
)
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_client: QdrantClient | None = None


@dataclass
class RetrievedChunk:
    text: str
    source: str
    score: float
    chunk_index: int


def _is_local() -> bool:
    """Local (on-disk) mode vs a remote server URL."""
    return not settings.qdrant_path.lower().startswith(("http://", "https://"))


def _index_tenant_fields(client: QdrantClient) -> None:
    """Index filter fields for tenant + platform scoped search."""
    for field in ("tenant_id", "company_id", "kb_scope", "doc_scope", "product"):
        client.create_payload_index(
            collection_name=settings.qdrant_collection,
            field_name=field,
            field_schema=qmodels.PayloadSchemaType.KEYWORD,
        )


def get_qdrant_client() -> QdrantClient:
    """Shared Qdrant client (KB + memory collections use the same instance)."""
    global _client
    if _client is None:
        if _is_local():
            _client = QdrantClient(path=settings.qdrant_path)
            logger.info("Opened Qdrant (local) at %s", settings.qdrant_path)
        else:
            _client = QdrantClient(url=settings.qdrant_path)
            logger.info("Connected Qdrant (server) at %s", settings.qdrant_path)
    return _client


def _get_client() -> QdrantClient:
    return get_qdrant_client()


def close() -> None:
    """Close the client (avoids a noisy destructor at interpreter shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _assert_vector_dims(vectors: list[list[float]]) -> None:
    expected = embeddings.embedding_dimension()
    for index, vector in enumerate(vectors):
        if len(vector) != expected:
            raise ValueError(
                f"Embedding dimension mismatch at chunk {index}: got {len(vector)}, "
                f"expected {expected}. Check OLLAMA_EMBED_MODEL matches the Qdrant "
                f"collection (run `python -m scripts.reset_vectors --yes` after changes)."
            )


def ensure_collection() -> None:
    """Create the collection if missing, sizing it from the embedding model.

    If the collection already exists, verify its vector size still matches the
    current embedding model. A mismatch means the embedding model changed (its
    dimension is baked into the collection and immutable in Qdrant), so fail
    with an actionable message instead of letting a later upsert raise an opaque
    Qdrant dimension error.
    """
    client = _get_client()
    if client.collection_exists(settings.qdrant_collection):
        existing = client.get_collection(settings.qdrant_collection)
        vectors = existing.config.params.vectors
        # Named-vector (hybrid) collections expose a dict; dense-only a single obj.
        existing_dim = vectors["dense"].size if isinstance(vectors, dict) else vectors.size
        current_dim = embeddings.embedding_dimension()
        is_hybrid_collection = isinstance(vectors, dict)
        if existing_dim != current_dim or is_hybrid_collection != settings.retrieval_hybrid:
            raise RuntimeError(
                f"Collection '{settings.qdrant_collection}' schema does not match the "
                f"current config (dim {existing_dim}->{current_dim}, hybrid "
                f"{is_hybrid_collection}->{settings.retrieval_hybrid}). Run "
                f"`python -m scripts.reset_vectors --yes` and re-ingest."
            )
        return
    dim = embeddings.embedding_dimension()
    if settings.retrieval_hybrid:
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config={"dense": qmodels.VectorParams(size=dim, distance=qmodels.Distance.COSINE)},
            sparse_vectors_config={"sparse": qmodels.SparseVectorParams(modifier=qmodels.Modifier.IDF)},
        )
        logger.info("Created HYBRID Qdrant collection '%s' (dim=%d + bm25)", settings.qdrant_collection, dim)
        if not _is_local():
            _index_tenant_fields(client)
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=qmodels.VectorParams(
            size=dim, distance=qmodels.Distance.COSINE
        ),
    )
    # Index tenant_id for fast filtered search (server only; local scans payload).
    if not _is_local():
        _index_tenant_fields(client)
    logger.info("Created Qdrant collection '%s' (dim=%d)", settings.qdrant_collection, dim)


def reset_collection() -> int:
    """Drop and recreate the collection, sized for the CURRENT embedding model.

    Wipes ALL tenants' chunks. Required when the embedding model's vector
    dimension changes (e.g. 4096 -> 1024), since a Qdrant collection's vector
    size is immutable. Returns the new dimension.

    Local on-disk Qdrant can keep stale index files after delete_collection();
    we remove the storage directory entirely to avoid dim/index corruption.
    """
    embeddings.reset_embedder()
    close()

    if _is_local():
        storage = Path(settings.qdrant_path)
        if storage.exists():
            shutil.rmtree(storage)
            logger.info("Removed local Qdrant storage at %s", storage)
    else:
        client = get_qdrant_client()
        for name in (settings.qdrant_collection, settings.qdrant_memory_collection):
            if client.collection_exists(name):
                client.delete_collection(name)
                logger.info("Dropped Qdrant collection '%s'", name)
        close()

    ensure_collection()
    return embeddings.embedding_dimension()


def _tenant_match(tenant_id: str) -> list[qmodels.FieldCondition]:
    """Dual-read: match the new ``tenant_id`` OR the legacy ``company_id`` payload.

    New points carry ``tenant_id``; data ingested before the rename only has
    ``company_id``. Run ``scripts.migrate_qdrant_payload`` to backfill, after which
    this can be narrowed to ``tenant_id`` only.
    """
    return [
        qmodels.FieldCondition(key="tenant_id", match=qmodels.MatchValue(value=tenant_id)),
        qmodels.FieldCondition(key="company_id", match=qmodels.MatchValue(value=tenant_id)),
    ]


def _kb_scope_match(kb_scope: str) -> list[qmodels.Condition]:
    """Match kb_scope; legacy points without the field count as support."""
    conditions: list[qmodels.Condition] = [
        qmodels.FieldCondition(key="kb_scope", match=qmodels.MatchValue(value=kb_scope)),
    ]
    if kb_scope == DEFAULT_KB_SCOPE:
        conditions.append(
            qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="kb_scope"))
        )
    return conditions


def _platform_retrieval_branch(product: str, kb_scope: str) -> qmodels.Filter:
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="doc_scope", match=qmodels.MatchValue(value=DOC_SCOPE_PLATFORM)
            ),
            qmodels.FieldCondition(key="product", match=qmodels.MatchValue(value=product)),
            qmodels.Filter(should=_kb_scope_match(kb_scope)),
        ]
    )


def _tenant_retrieval_branch(tenant_id: str, kb_scope: str) -> qmodels.Filter:
    """Tenant-owned chunks (explicit ``doc_scope=tenant`` or legacy rows without doc_scope)."""
    return qmodels.Filter(
        must=[
            qmodels.Filter(should=_tenant_match(tenant_id)),
            qmodels.Filter(should=_kb_scope_match(kb_scope)),
            qmodels.Filter(
                should=[
                    qmodels.FieldCondition(
                        key="doc_scope", match=qmodels.MatchValue(value=DOC_SCOPE_TENANT)
                    ),
                    qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="doc_scope")),
                ]
            ),
        ]
    )


def _retrieval_filter(tenant_id: str, kb_scope: str, product: str) -> qmodels.Filter:
    """Platform shared docs OR tenant-owned docs for the same product scope."""
    product_slug = product if product in KNOWN_PRODUCTS else "lms"
    return qmodels.Filter(
        should=[
            _platform_retrieval_branch(product_slug, kb_scope),
            _tenant_retrieval_branch(tenant_id, kb_scope),
        ]
    )


def _legacy_retrieval_filter(tenant_id: str, kb_scope: str) -> qmodels.Filter:
    """Pre-platform retrieval (tenant_id + kb_scope only)."""
    return qmodels.Filter(
        must=[
            qmodels.Filter(should=_tenant_match(tenant_id)),
            qmodels.Filter(should=_kb_scope_match(kb_scope)),
        ]
    )


def _query_filter(
    tenant_id: str,
    kb_scope: str,
    product: str | None,
    *,
    retrieval_profile: str = RETRIEVAL_PLATFORM_AND_TENANT,
) -> qmodels.Filter:
    """Build Qdrant filter for the requested retrieval layer."""
    if retrieval_profile == RETRIEVAL_PLATFORM_ONLY:
        product_slug = product if product in KNOWN_PRODUCTS else PRODUCT_LMS
        return _platform_retrieval_branch(product_slug, kb_scope)
    if retrieval_profile == RETRIEVAL_TENANT_ONLY:
        return _tenant_retrieval_branch(tenant_id, kb_scope)
    if product:
        product_slug = product if product in KNOWN_PRODUCTS else PRODUCT_LMS
        return _retrieval_filter(tenant_id, kb_scope, product_slug)
    return _legacy_retrieval_filter(tenant_id, kb_scope)


def delete_by_source(tenant_id: str, source: str, kb_scope: str = DEFAULT_KB_SCOPE) -> None:
    """Remove tenant-owned chunks for a document within a KB scope."""
    client = _get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.Filter(
            must=[
                qmodels.FieldCondition(key="source", match=qmodels.MatchValue(value=source)),
                qmodels.Filter(should=_tenant_match(tenant_id)),
                qmodels.Filter(should=_kb_scope_match(kb_scope)),
                qmodels.Filter(
                    should=[
                        qmodels.FieldCondition(
                            key="doc_scope", match=qmodels.MatchValue(value=DOC_SCOPE_TENANT)
                        ),
                        qmodels.IsEmptyCondition(is_empty=qmodels.PayloadField(key="doc_scope")),
                    ]
                ),
            ],
        ),
    )


def delete_by_platform_external_id(product: str, external_id: str) -> None:
    """Remove all platform chunks for one parent-company document."""
    client = _get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="doc_scope", match=qmodels.MatchValue(value=DOC_SCOPE_PLATFORM)
                ),
                qmodels.FieldCondition(key="product", match=qmodels.MatchValue(value=product)),
                qmodels.FieldCondition(
                    key="external_id", match=qmodels.MatchValue(value=external_id)
                ),
            ],
        ),
    )


def delete_points(vector_ids: list[str]) -> None:
    """Remove Qdrant points by id (document delete)."""
    if not vector_ids:
        return
    client = _get_client()
    if not client.collection_exists(settings.qdrant_collection):
        return
    client.delete(
        collection_name=settings.qdrant_collection,
        points_selector=qmodels.PointIdsList(points=vector_ids),
    )


def upsert_chunks(
    tenant_id: str,
    source: str,
    chunks: list[str],
    vectors: list[list[float]],
    vector_ids: list[str] | None = None,
    *,
    kb_scope: str = DEFAULT_KB_SCOPE,
) -> list[str]:
    """Store embedded chunks for a tenant's document. Returns the point ids.

    Replaces any existing chunks for the same (tenant, kb_scope, source) so
    re-uploading a file in the same KB doesn't create duplicates.
    """
    if not chunks:
        return []
    ensure_collection()
    _assert_vector_dims(vectors)
    delete_by_source(tenant_id, source, kb_scope)
    client = _get_client()

    ids = vector_ids or [str(uuid.uuid4()) for _ in chunks]

    def _payload(index: int, text: str) -> dict:
        return {
            "doc_scope": DOC_SCOPE_TENANT,
            "tenant_id": tenant_id,
            "kb_scope": kb_scope,
            "source": source,
            "chunk_index": index,
            "text": text,
        }

    if settings.retrieval_hybrid:
        from app.modules.knowledge.rag import sparse

        sparse_vecs = sparse.embed_documents(chunks)
        points = [
            qmodels.PointStruct(
                id=ids[index],
                vector={
                    "dense": vector,
                    "sparse": qmodels.SparseVector(indices=s_idx, values=s_val),
                },
                payload=_payload(index, text),
            )
            for index, (text, vector, (s_idx, s_val)) in enumerate(zip(chunks, vectors, sparse_vecs))
        ]
    else:
        points = [
            qmodels.PointStruct(id=ids[index], vector=vector, payload=_payload(index, text))
            for index, (text, vector) in enumerate(zip(chunks, vectors))
        ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info(
        "Upserted %d chunks for tenant=%s kb_scope=%s source=%s",
        len(points), tenant_id, kb_scope, source,
    )
    return ids


def upsert_platform_chunks(
    *,
    product: str,
    external_id: str,
    source: str,
    source_type: str,
    chunks: list[str],
    vectors: list[list[float]],
    kb_scope: str = DEFAULT_KB_SCOPE,
    vector_ids: list[str] | None = None,
) -> list[str]:
    """Store embedded chunks for a parent-company document (shared by all tenants)."""
    if not chunks:
        return []
    ensure_collection()
    _assert_vector_dims(vectors)
    delete_by_platform_external_id(product, external_id)
    client = _get_client()
    ids = vector_ids or [str(uuid.uuid4()) for _ in chunks]

    def _payload(index: int, text: str) -> dict:
        return {
            "doc_scope": DOC_SCOPE_PLATFORM,
            "product": product,
            "kb_scope": kb_scope,
            "source_type": source_type,
            "external_id": external_id,
            "source": source,
            "chunk_index": index,
            "text": text,
        }

    if settings.retrieval_hybrid:
        from app.modules.knowledge.rag import sparse

        sparse_vecs = sparse.embed_documents(chunks)
        points = [
            qmodels.PointStruct(
                id=ids[index],
                vector={
                    "dense": vector,
                    "sparse": qmodels.SparseVector(indices=s_idx, values=s_val),
                },
                payload=_payload(index, text),
            )
            for index, (text, vector, (s_idx, s_val)) in enumerate(zip(chunks, vectors, sparse_vecs))
        ]
    else:
        points = [
            qmodels.PointStruct(id=ids[index], vector=vector, payload=_payload(index, text))
            for index, (text, vector) in enumerate(zip(chunks, vectors))
        ]
    client.upsert(collection_name=settings.qdrant_collection, points=points)
    logger.info(
        "Upserted %d platform chunks product=%s kb_scope=%s external_id=%s",
        len(points), product, kb_scope, external_id,
    )
    return ids


def _to_chunks(points) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(
            text=hit.payload.get("text", ""),
            source=hit.payload.get("source", ""),
            score=hit.score,
            chunk_index=hit.payload.get("chunk_index", -1),
        )
        for hit in points
    ]


def search(
    tenant_id: str,
    query_vector: list[float],
    top_k: int,
    *,
    kb_scope: str = DEFAULT_KB_SCOPE,
    product: str | None = None,
    retrieval_profile: str = RETRIEVAL_PLATFORM_AND_TENANT,
) -> list[RetrievedChunk]:
    """Dense search with agent-specific retrieval scope."""
    ensure_collection()
    client = _get_client()
    query_filter = _query_filter(
        tenant_id, kb_scope, product, retrieval_profile=retrieval_profile
    )
    using = "dense" if settings.retrieval_hybrid else None
    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        query=query_vector,
        using=using,
        query_filter=query_filter,
        limit=top_k,
        with_payload=True,
    ).points
    return _to_chunks(hits)


def search_hybrid(
    tenant_id: str,
    dense_vector: list[float],
    sparse_query: tuple[list[int], list[float]],
    top_k: int,
    *,
    kb_scope: str = DEFAULT_KB_SCOPE,
    product: str | None = None,
    retrieval_profile: str = RETRIEVAL_PLATFORM_AND_TENANT,
) -> list[RetrievedChunk]:
    """Hybrid search with agent-specific retrieval scope."""
    ensure_collection()
    client = _get_client()
    query_filter = _query_filter(
        tenant_id, kb_scope, product, retrieval_profile=retrieval_profile
    )
    s_idx, s_val = sparse_query
    prefetch = [
        qmodels.Prefetch(query=dense_vector, using="dense", filter=query_filter, limit=top_k),
        qmodels.Prefetch(
            query=qmodels.SparseVector(indices=s_idx, values=s_val),
            using="sparse", filter=query_filter, limit=top_k,
        ),
    ]
    hits = client.query_points(
        collection_name=settings.qdrant_collection,
        prefetch=prefetch,
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=top_k,
        with_payload=True,
    ).points
    return _to_chunks(hits)
