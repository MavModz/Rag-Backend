"""Conversation ORM models: chat sessions and persisted messages.

Bot replies are persisted here (they were not before). ``tenant_id`` scopes every
row; ``session_id`` groups a conversation. ``external_user_id`` is the id of the
user in the source business system (e.g. a WhatsApp phone number).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Session(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "sessions"

    external_user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(32), default="web", nullable=False)
    last_active: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Message(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
