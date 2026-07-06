"""Connector ORM model: per-tenant external data-source configuration.

Drives the ConnectorRegistry (Phase 5). Each row says which external system a
tenant's business data lives in (``type`` = mongo | mysql | ...), how to connect
(``config``), and how to map platform fields to the source's fields
(``field_mapping``, e.g. tenant_id -> company_id). Secrets in ``config`` should be
stored encrypted in production.
"""
from __future__ import annotations

from sqlalchemy import Boolean, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class DataSource(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "data_sources"

    type: Mapped[str] = mapped_column(String(32), nullable=False)  # mongo | mysql | ...
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    field_mapping: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
