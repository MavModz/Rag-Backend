"""Conversation persistence: sessions and messages (Postgres)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversation.models import Message, Session


async def get_or_create_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    external_user_id: str,
    channel: str = "web",
) -> Session:
    res = await session.execute(
        select(Session).where(
            Session.tenant_id == tenant_id,
            Session.external_user_id == external_user_id,
            Session.channel == channel,
        )
    )
    row = res.scalars().first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = Session(
            tenant_id=tenant_id, external_user_id=external_user_id, channel=channel, last_active=now
        )
        session.add(row)
        await session.flush()
    else:
        row.last_active = now
    return row


async def add_message(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    role: str,
    content: str,
    sources: list[str] | None = None,
    model: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> Message:
    msg = Message(
        tenant_id=tenant_id,
        session_id=session_id,
        role=role,
        content=content,
        sources=sources or [],
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    session.add(msg)
    await session.flush()
    return msg
