"""Job ORM model — tracks background work status/results across backends."""
from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Job(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "jobs"

    type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", index=True, nullable=False
    )  # pending | running | completed | failed
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
