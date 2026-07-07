"""cross-platform provisioning columns and identity indexes

Revision ID: f2a8b91c04d3
Revises: e1f4c63b2152
Create Date: 2026-07-07 16:50:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f2a8b91c04d3"
down_revision: str | None = "e1f4c63b2152"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.add_column(sa.Column("lms_institute_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("crm_company_id", sa.String(length=24), nullable=True))

    op.create_index(
        "uq_tenants_lms_institute_id",
        "tenants",
        ["lms_institute_id"],
        unique=True,
        postgresql_where=sa.text("lms_institute_id IS NOT NULL"),
    )
    op.create_index(
        "uq_tenants_crm_company_id",
        "tenants",
        ["crm_company_id"],
        unique=True,
        postgresql_where=sa.text("crm_company_id IS NOT NULL"),
    )

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "external_role_label",
                sa.String(length=64),
                nullable=False,
                server_default="admin",
            )
        )
        batch_op.add_column(sa.Column("lms_user_id", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("crm_user_id", sa.String(length=24), nullable=True))

    op.alter_column("users", "external_role_label", server_default=None)

    op.create_index(
        "uq_users_provisioning_identity",
        "users",
        [sa.text("lower(email)"), "phone", "external_role_label"],
        unique=True,
    )
    op.create_index(
        "uq_users_lms_user_id",
        "users",
        ["lms_user_id"],
        unique=True,
        postgresql_where=sa.text("lms_user_id IS NOT NULL"),
    )
    op.create_index(
        "uq_users_crm_user_id",
        "users",
        ["crm_user_id"],
        unique=True,
        postgresql_where=sa.text("crm_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_crm_user_id", table_name="users")
    op.drop_index("uq_users_lms_user_id", table_name="users")
    op.drop_index("uq_users_provisioning_identity", table_name="users")

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_column("crm_user_id")
        batch_op.drop_column("lms_user_id")
        batch_op.drop_column("external_role_label")

    op.drop_index("uq_tenants_crm_company_id", table_name="tenants")
    op.drop_index("uq_tenants_lms_institute_id", table_name="tenants")

    with op.batch_alter_table("tenants", schema=None) as batch_op:
        batch_op.drop_column("crm_company_id")
        batch_op.drop_column("lms_institute_id")
