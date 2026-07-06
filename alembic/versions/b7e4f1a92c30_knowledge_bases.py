"""knowledge_bases + documents table

Revision ID: b7e4f1a92c30
Revises: a3f8c2d91e04
Create Date: 2026-06-30 14:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b7e4f1a92c30"
down_revision: str | None = "a3f8c2d91e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_bases")),
        sa.UniqueConstraint("tenant_id", "scope", name="uq_knowledge_bases_tenant_scope"),
    )
    with op.batch_alter_table("knowledge_bases", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_knowledge_bases_scope"), ["scope"], unique=False)
        batch_op.create_index(batch_op.f("ix_knowledge_bases_tenant_id"), ["tenant_id"], unique=False)

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("knowledge_base_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_documents_knowledge_base_id_knowledge_bases"),
            "knowledge_bases",
            ["knowledge_base_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_documents_knowledge_base_id"), ["knowledge_base_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_documents_knowledge_base_id"))
        batch_op.drop_constraint(
            batch_op.f("fk_documents_knowledge_base_id_knowledge_bases"), type_="foreignkey"
        )
        batch_op.drop_column("knowledge_base_id")
    op.drop_table("knowledge_bases")
