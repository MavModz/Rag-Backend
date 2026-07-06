"""tenants.external_org_id for LMS/CRM JWT org_id mapping

Revision ID: c8d2a41f03b1
Revises: b7e4f1a92c30
Create Date: 2026-07-01 16:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c8d2a41f03b1"
down_revision: str | None = "b7e4f1a92c30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column("external_org_id", sa.String(length=128), nullable=True),
    )
    op.create_index("ix_tenants_external_org_id", "tenants", ["external_org_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_tenants_external_org_id", table_name="tenants")
    op.drop_column("tenants", "external_org_id")
