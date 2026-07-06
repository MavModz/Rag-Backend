"""Chatbot configuration persistence."""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from sqlalchemy import select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatbot.exceptions import ChatbotSchemaNotReadyError
from app.modules.chatbot.models import ChatbotConfig

P = ParamSpec("P")
R = TypeVar("R")

_SCHEMA_MSG = (
    "Chatbot database schema is not ready. Run `alembic upgrade head` on the AI server."
)


def _is_missing_chatbot_table(exc: ProgrammingError) -> bool:
    orig = getattr(exc, "orig", None)
    name = type(orig).__name__ if orig is not None else ""
    text = str(orig or exc).lower()
    return name == "UndefinedTableError" or (
        "chatbot_configs" in text and "does not exist" in text
    )


def _translate_schema_errors(
    func: Callable[P, Awaitable[R]],
) -> Callable[P, Awaitable[R]]:
    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await func(*args, **kwargs)
        except ProgrammingError as exc:
            if _is_missing_chatbot_table(exc):
                raise ChatbotSchemaNotReadyError(_SCHEMA_MSG) from exc
            raise

    return wrapper


@_translate_schema_errors
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


@_translate_schema_errors
async def create_default(
    session: AsyncSession, tenant_id: uuid.UUID, channel: str
) -> ChatbotConfig:
    row = ChatbotConfig(tenant_id=tenant_id, channel=channel)
    session.add(row)
    await session.flush()
    return row
