"""Chatbot configuration persistence."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatbot.models import ChatbotConfig


async def get_by_tenant_channel(
    session: AsyncSession, tenant_id: uuid.UUID, channel: str
) -> ChatbotConfig | None:
    result = await session.execute(
        select(ChatbotConfig).where(
            ChatbotConfig.tenant_id == tenant_id,
            ChatbotConfig.channel == channel,
        )
    )
    return result.scalars().first()


async def create_default(
    session: AsyncSession, tenant_id: uuid.UUID, channel: str
) -> ChatbotConfig:
    row = ChatbotConfig(tenant_id=tenant_id, channel=channel)
    session.add(row)
    await session.flush()
    return row
