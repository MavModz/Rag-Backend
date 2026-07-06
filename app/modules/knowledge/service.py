"""Knowledge Service — ingestion orchestration: load -> chunk -> embed -> store."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from app.modules.knowledge.constants import (
    DEFAULT_KB_SCOPE,
    DOC_SCOPE_TENANT,
    SOURCE_TYPE_FILE,
)
from app.modules.knowledge.rag import chunker, embeddings, loaders, vector_store
from app.platform.observability.logging import get_logger
from app.platform.tenancy.constants import KNOWN_PRODUCTS

logger = get_logger(__name__)


@dataclass
class IngestionResult:
    source: str
    chunks_indexed: int
    kb_scope: str = DEFAULT_KB_SCOPE
    vector_ids: list[str] = field(default_factory=list)
    chunk_previews: list[str] = field(default_factory=list)


@dataclass
class PlatformIngestionResult:
    product: str
    external_id: str
    source: str
    title: str
    source_type: str
    chunks_indexed: int
    kb_scope: str = DEFAULT_KB_SCOPE
    content_hash: str = ""
    vector_ids: list[str] = field(default_factory=list)
    chunk_previews: list[str] = field(default_factory=list)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_product(product: str) -> str:
    slug = product.strip().lower()
    if slug not in KNOWN_PRODUCTS:
        raise ValueError(f"product must be one of {sorted(KNOWN_PRODUCTS)}")
    return slug


def ingest_file(
    file_path: str | Path, tenant_id: str, kb_scope: str = DEFAULT_KB_SCOPE
) -> IngestionResult:
    """Ingest one tenant-owned document into the vector store."""
    source = Path(file_path).name
    text = loaders.load_document(file_path)
    chunks = chunker.chunk_text(text)
    if not chunks:
        logger.warning("No chunks produced for %s", source)
        return IngestionResult(source=source, chunks_indexed=0, kb_scope=kb_scope)

    vectors = embeddings.embed_documents(chunks)
    vector_ids = vector_store.upsert_chunks(
        tenant_id=tenant_id,
        source=source,
        chunks=chunks,
        vectors=vectors,
        kb_scope=kb_scope,
    )
    return IngestionResult(
        source=source,
        chunks_indexed=len(vector_ids),
        kb_scope=kb_scope,
        vector_ids=vector_ids,
        chunk_previews=chunks,
    )


def ingest_platform_text(
    *,
    product: str,
    text: str,
    title: str,
    external_id: str,
    kb_scope: str = DEFAULT_KB_SCOPE,
    source_type: str = SOURCE_TYPE_FILE,
    source: str | None = None,
) -> PlatformIngestionResult:
    """Ingest parent-company text (from API HTML/markdown or extracted file)."""
    product_slug = _normalize_product(product)
    ext_id = external_id.strip()
    if not ext_id:
        raise ValueError("external_id is required")
    display_source = source or title or ext_id
    digest = content_hash(text)
    chunks = chunker.chunk_text(text)
    if not chunks:
        logger.warning("No chunks produced for platform doc %s", ext_id)
        return PlatformIngestionResult(
            product=product_slug,
            external_id=ext_id,
            source=display_source,
            title=title,
            source_type=source_type,
            chunks_indexed=0,
            kb_scope=kb_scope,
            content_hash=digest,
        )

    vectors = embeddings.embed_documents(chunks)
    vector_ids = vector_store.upsert_platform_chunks(
        product=product_slug,
        external_id=ext_id,
        source=display_source,
        source_type=source_type,
        chunks=chunks,
        vectors=vectors,
        kb_scope=kb_scope,
    )
    return PlatformIngestionResult(
        product=product_slug,
        external_id=ext_id,
        source=display_source,
        title=title,
        source_type=source_type,
        chunks_indexed=len(vector_ids),
        kb_scope=kb_scope,
        content_hash=digest,
        vector_ids=vector_ids,
        chunk_previews=chunks,
    )


def ingest_platform_file(
    file_path: str | Path,
    *,
    product: str,
    kb_scope: str = DEFAULT_KB_SCOPE,
    external_id: str | None = None,
    title: str | None = None,
) -> PlatformIngestionResult:
    """Ingest a parent-company PDF/DOCX shared across all tenants."""
    path = Path(file_path)
    source = path.name
    ext_id = external_id or path.stem
    text = loaders.load_document(path)
    return ingest_platform_text(
        product=product,
        text=text,
        title=title or source,
        external_id=ext_id,
        kb_scope=kb_scope,
        source_type=SOURCE_TYPE_FILE,
        source=source,
    )
