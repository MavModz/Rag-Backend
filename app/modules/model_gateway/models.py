"""Model Gateway ORM models: model registry, AI usage, prompts, configuration.

``ModelRegistry`` makes model profiles editable without a redeploy. ``AiUsage`` is
the per-tenant/per-call usage+cost ledger written by the gateway usage hook.
``PromptTemplate`` / ``Configuration`` allow global defaults (``tenant_id`` NULL)
overridden per tenant.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Float, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class ModelRegistry(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "model_registry"

    profile_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    fallback_profile: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_per_1k_in: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_per_1k_out: Mapped[float | None] = mapped_column(Float, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AiUsage(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_usage"

    profile: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class PromptTemplate(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "prompt_templates"

    # NULL tenant_id = global default; a tenant row overrides it.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    key: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)


class Configuration(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "configurations"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    key: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
