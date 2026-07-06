"""memories table for chat learnings

Revision ID: a3f8c2d91e04
Revises: 7c14aa13c4bd
Create Date: 2026-06-30 12:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a3f8c2d91e04"
down_revision: str | None = "7c14aa13c4bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "memories",
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("memory_type", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source_question", sa.Text(), nullable=True),
        sa.Column("vector_id", sa.String(length=64), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"], ["sessions.id"], name=op.f("fk_memories_session_id_sessions"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memories")),
    )
    with op.batch_alter_table("memories", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_memories_external_user_id"), ["external_user_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_memories_memory_type"), ["memory_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_memories_session_id"), ["session_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_memories_tenant_id"), ["tenant_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_memories_vector_id"), ["vector_id"], unique=False)


def downgrade() -> None:
    op.drop_table("memories")
