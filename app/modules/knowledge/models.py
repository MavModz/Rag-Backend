"""Knowledge ORM models: knowledge bases, document records, and chunk metadata.

Postgres is the system of record for *what* has been ingested; chunk vectors
live in Qdrant. ``DocumentChunk.vector_id`` links the two stores. ``tenant_id``
scopes every row; ``KnowledgeBase.scope`` partitions documents per agent use-case.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class KnowledgeBase(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "knowledge_bases"
    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", name="uq_knowledge_bases_tenant_scope"),
    )

    scope: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Document(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "documents"

    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True, nullable=True
    )
    source: Mapped[str] = mapped_column(String(512), index=True, nullable=False)  # filename
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    mime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="indexed", nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class DocumentChunk(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "document_chunks"

    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # Qdrant point id
    text_preview: Mapped[str | None] = mapped_column(Text, nullable=True)


class PlatformDocument(UUIDMixin, TimestampMixin, Base):
    """Parent-company manuals and KB content shared across all tenants."""

    __tablename__ = "platform_documents"
    __table_args__ = (
        UniqueConstraint("product", "external_id", name="uq_platform_documents_product_external"),
    )

    product: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    kb_scope: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # file | api
    external_id: Mapped[str] = mapped_column(String(256), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(512), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(String(1024), nullable=True)
