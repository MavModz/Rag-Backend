"""Platform (parent-company) document registry — shared across all tenants."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.knowledge.models import PlatformDocument


async def get_by_external_id(
    session: AsyncSession, product: str, external_id: str
) -> PlatformDocument | None:
    return (
        await session.execute(
            select(PlatformDocument).where(
                PlatformDocument.product == product,
                PlatformDocument.external_id == external_id,
            )
        )
    ).scalar_one_or_none()


async def upsert_platform_document(
    session: AsyncSession,
    *,
    product: str,
    kb_scope: str,
    source_type: str,
    external_id: str,
    title: str,
    source: str,
    content_hash: str | None,
    chunk_count: int,
    storage_uri: str | None = None,
) -> PlatformDocument:
    row = await get_by_external_id(session, product, external_id)
    if row is None:
        row = PlatformDocument(
            product=product,
            kb_scope=kb_scope,
            source_type=source_type,
            external_id=external_id,
            title=title,
            source=source,
            content_hash=content_hash,
            chunk_count=chunk_count,
            storage_uri=storage_uri,
        )
        session.add(row)
    else:
        row.kb_scope = kb_scope
        row.source_type = source_type
        row.title = title
        row.source = source
        row.content_hash = content_hash
        row.chunk_count = chunk_count
        if storage_uri is not None:
            row.storage_uri = storage_uri
    await session.flush()
    return row


async def list_platform_documents(
    session: AsyncSession, product: str | None = None
) -> list[PlatformDocument]:
    stmt = select(PlatformDocument).order_by(
        PlatformDocument.product, PlatformDocument.title
    )
    if product:
        stmt = stmt.where(PlatformDocument.product == product)
    return list((await session.execute(stmt)).scalars().all())


async def delete_platform_document(
    session: AsyncSession, document_id: uuid.UUID
) -> PlatformDocument | None:
    row = await session.get(PlatformDocument, document_id)
    if row is None:
        return None
    await session.delete(row)
    await session.flush()
    return row
