"""drop legacy tenants.external_org_id

Revision ID: g3c7d82e15a4
Revises: f2a8b91c04d3
Create Date: 2026-07-07 17:30:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "g3c7d82e15a4"
down_revision: str | None = "f2a8b91c04d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_tenants_external_org_id", table_name="tenants")
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("external_org_id")


def downgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_org_id", sa.String(length=128), nullable=True))
    op.create_index("ix_tenants_external_org_id", "tenants", ["external_org_id"], unique=True)
