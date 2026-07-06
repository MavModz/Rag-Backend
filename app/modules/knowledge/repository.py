"""Knowledge persistence: knowledge bases, documents, and chunk metadata."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.constants import DEFAULT_KNOWLEDGE_BASES, DEFAULT_KB_SCOPE, KNOWN_KB_SCOPES
from app.modules.knowledge.models import Document, DocumentChunk, KnowledgeBase


async def ensure_default_knowledge_bases(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Create default agent-scoped KB rows for a tenant (idempotent)."""
    for scope, name, description in DEFAULT_KNOWLEDGE_BASES:
        existing = (
            await session.execute(
                select(KnowledgeBase).where(
                    KnowledgeBase.tenant_id == tenant_id,
                    KnowledgeBase.scope == scope,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                KnowledgeBase(
                    tenant_id=tenant_id,
                    scope=scope,
                    name=name,
                    description=description,
                )
            )
    await session.flush()


async def get_knowledge_base_by_scope(
    session: AsyncSession, tenant_id: uuid.UUID, scope: str
) -> KnowledgeBase | None:
    return (
        await session.execute(
            select(KnowledgeBase).where(
                KnowledgeBase.tenant_id == tenant_id,
                KnowledgeBase.scope == scope,
            )
        )
    ).scalar_one_or_none()


async def get_or_create_knowledge_base(
    session: AsyncSession, tenant_id: uuid.UUID, scope: str
) -> KnowledgeBase:
    if scope not in KNOWN_KB_SCOPES:
        raise ValueError(f"Unknown knowledge base scope: {scope!r}")
    row = await get_knowledge_base_by_scope(session, tenant_id, scope)
    if row is not None:
        return row
    await ensure_default_knowledge_bases(session, tenant_id)
    row = await get_knowledge_base_by_scope(session, tenant_id, scope)
    if row is None:
        raise ValueError(f"Knowledge base scope {scope!r} is not available for this tenant")
    return row


async def list_knowledge_bases(session: AsyncSession, tenant_id: uuid.UUID) -> list[KnowledgeBase]:
    await ensure_default_knowledge_bases(session, tenant_id)
    result = await session.execute(
        select(KnowledgeBase)
        .where(KnowledgeBase.tenant_id == tenant_id)
        .order_by(KnowledgeBase.scope)
    )
    return list(result.scalars().all())


async def list_documents_for_scope(
    session: AsyncSession, tenant_id: uuid.UUID, scope: str
) -> list[Document]:
    kb = await get_or_create_knowledge_base(session, tenant_id, scope)
    result = await session.execute(
        select(Document)
        .where(Document.tenant_id == tenant_id, Document.knowledge_base_id == kb.id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> Document | None:
    return (
        await session.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.id == document_id,
            )
        )
    ).scalar_one_or_none()


async def create_document(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    knowledge_base_id: uuid.UUID,
    source: str,
    filename: str,
    mime: str | None,
    storage_uri: str | None,
    chunk_count: int,
) -> Document:
    doc = Document(
        tenant_id=tenant_id,
        knowledge_base_id=knowledge_base_id,
        source=source,
        filename=filename,
        mime=mime,
        storage_uri=storage_uri,
        status="indexed",
        chunk_count=chunk_count,
    )
    session.add(doc)
    await session.flush()
    return doc


async def add_chunks(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    vector_ids: list[str],
    previews: list[str],
) -> int:
    for index, vector_id in enumerate(vector_ids):
        preview = previews[index][:500] if index < len(previews) else None
        session.add(
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document_id,
                chunk_index=index,
                vector_id=vector_id,
                text_preview=preview,
            )
        )
    return len(vector_ids)


async def delete_document(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID
) -> list[str]:
    """Delete a document row and return its Qdrant vector ids for cleanup."""
    doc = await get_document(session, tenant_id, document_id)
    if doc is None:
        return []
    vector_ids = list(
        (
            await session.execute(
                select(DocumentChunk.vector_id).where(
                    DocumentChunk.tenant_id == tenant_id,
                    DocumentChunk.document_id == document_id,
                )
            )
        ).scalars().all()
    )
    await session.delete(doc)
    await session.flush()
    return vector_ids


def normalize_kb_scope(scope: str | None) -> str:
    """Validate and normalize kb_scope; default to support."""
    value = (scope or DEFAULT_KB_SCOPE).strip().lower()
    if value not in KNOWN_KB_SCOPES:
        raise ValueError(f"kb_scope must be one of {sorted(KNOWN_KB_SCOPES)}")
    return value
