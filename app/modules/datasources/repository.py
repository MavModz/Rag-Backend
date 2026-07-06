"""Data-source persistence (tenant-scoped)."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.connectors.models import DataSource


async def list_for_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> list[DataSource]:
    res = await session.execute(
        select(DataSource)
        .where(DataSource.tenant_id == tenant_id)
        .order_by(DataSource.created_at.asc())
    )
    return list(res.scalars().all())


async def get_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID, source_id: uuid.UUID
) -> DataSource | None:
    src = await session.get(DataSource, source_id)
    if src is None or src.tenant_id != tenant_id:
        return None
    return src


async def add(session: AsyncSession, src: DataSource) -> DataSource:
    session.add(src)
    await session.flush()
    return src


async def delete(session: AsyncSession, src: DataSource) -> None:
    await session.delete(src)
