"""platform_documents table for parent-company shared content

Revision ID: d9e3b52a1041
Revises: c8d2a41f03b1
Create Date: 2026-07-02 10:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d9e3b52a1041"
down_revision: str | None = "c8d2a41f03b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("product", sa.String(length=16), nullable=False),
        sa.Column("kb_scope", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=16), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("source", sa.String(length=512), nullable=False),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("storage_uri", sa.String(length=1024), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product", "external_id", name="uq_platform_documents_product_external"),
    )
    op.create_index("ix_platform_documents_product", "platform_documents", ["product"])
    op.create_index("ix_platform_documents_kb_scope", "platform_documents", ["kb_scope"])
    op.create_index("ix_platform_documents_external_id", "platform_documents", ["external_id"])


def downgrade() -> None:
    op.drop_index("ix_platform_documents_external_id", table_name="platform_documents")
    op.drop_index("ix_platform_documents_kb_scope", table_name="platform_documents")
    op.drop_index("ix_platform_documents_product", table_name="platform_documents")
    op.drop_table("platform_documents")
