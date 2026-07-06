"""Memory ORM: distilled learnings from past chats (tenant-scoped).

Postgres is the system of record; vectors live in the Qdrant ``memory`` collection.
``vector_id`` links the two stores.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin

MEMORY_TYPE_INSIGHT = "insight"
MEMORY_TYPE_VERIFIED_QA = "verified_qa"


class Memory(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "memories"

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sessions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    external_user_id: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    memory_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    vector_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
