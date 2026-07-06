"""chatbot_configs table for per-tenant WhatsApp behavior settings

Revision ID: e1f4c63b2152
Revises: d9e3b52a1041
Create Date: 2026-07-05 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "e1f4c63b2152"
down_revision: str | None = "d9e3b52a1041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chatbot_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False, server_default="whatsapp"),
        sa.Column("name", sa.String(length=128), nullable=False, server_default="WhatsApp Bot"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("tone", sa.String(length=32), nullable=False, server_default="friendly"),
        sa.Column("goals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("conversion", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("greeting_message", sa.Text(), nullable=True),
        sa.Column("fallback_message", sa.Text(), nullable=True),
        sa.Column("handoff_keywords", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("kb_scope", sa.String(length=64), nullable=False, server_default="support"),
        sa.Column("product", sa.String(length=16), nullable=False, server_default="crm"),
        sa.Column("model_profile", sa.String(length=128), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "channel", name="uq_chatbot_configs_tenant_channel"),
    )
    op.create_index("ix_chatbot_configs_tenant_id", "chatbot_configs", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_chatbot_configs_tenant_id", table_name="chatbot_configs")
    op.drop_table("chatbot_configs")
