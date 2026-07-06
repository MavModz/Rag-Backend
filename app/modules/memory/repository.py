"""Memory persistence (Postgres, tenant-scoped)."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.memory.models import Memory


async def create_memory(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    memory_type: str,
    summary: str,
    vector_id: str,
    session_id: uuid.UUID | None = None,
    external_user_id: str | None = None,
    source_question: str | None = None,
) -> Memory:
    row = Memory(
        tenant_id=tenant_id,
        session_id=session_id,
        external_user_id=external_user_id,
        memory_type=memory_type,
        summary=summary,
        source_question=source_question,
        vector_id=vector_id,
    )
    session.add(row)
    await session.flush()
    return row
