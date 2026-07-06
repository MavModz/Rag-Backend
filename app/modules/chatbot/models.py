"""Chatbot configuration ORM — per-tenant, per-channel behavior settings."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ChatbotConfig(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "chatbot_configs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "channel", name="uq_chatbot_configs_tenant_channel"),
    )

    channel: Mapped[str] = mapped_column(String(32), default="whatsapp", nullable=False)
    name: Mapped[str] = mapped_column(String(128), default="WhatsApp Bot", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    tone: Mapped[str] = mapped_column(String(32), default="friendly", nullable=False)
    goals: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    conversion: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    greeting_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    handoff_keywords: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    kb_scope: Mapped[str] = mapped_column(String(64), default="support", nullable=False)
    product: Mapped[str] = mapped_column(String(16), default="crm", nullable=False)
    model_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
