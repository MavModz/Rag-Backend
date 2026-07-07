"""Identity ORM models: tenants, users, roles, API keys, audit logs.

These tables are the platform's source of truth for *who* is calling and *which
tenant* they belong to. Cross-module tables reference tenants by plain
``tenant_id`` (no FK) so services stay extractable; within this module FKs are
used freely.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.platform.db.base import Base, TenantMixin, TimestampMixin, UUIDMixin


class Tenant(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tenants"
    __table_args__ = (
        Index(
            "uq_tenants_lms_institute_id",
            "lms_institute_id",
            unique=True,
            postgresql_where=text("lms_institute_id IS NOT NULL"),
        ),
        Index(
            "uq_tenants_crm_company_id",
            "crm_company_id",
            unique=True,
            postgresql_where=text("crm_company_id IS NOT NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    budget_monthly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lms_institute_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    crm_company_id: Mapped[str | None] = mapped_column(String(24), nullable=True)


class Role(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Flat list of permission strings (e.g. "chat:write"). A dedicated
    # permissions table is deferred past M1.
    permissions: Mapped[list] = mapped_column(JSON, default=list, nullable=False)


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"
    # Per-tenant uniqueness for tenant-admin-created members; cross-product
    # provisioning also keys on (email, phone, external_role_label) globally.
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
        UniqueConstraint("tenant_id", "phone", name="uq_users_tenant_phone"),
        Index(
            "uq_users_provisioning_identity",
            func.lower(Column("email", String(255))),
            "phone",
            "external_role_label",
            unique=True,
        ),
        Index(
            "uq_users_lms_user_id",
            "lms_user_id",
            unique=True,
            postgresql_where=text("lms_user_id IS NOT NULL"),
        ),
        Index(
            "uq_users_crm_user_id",
            "crm_user_id",
            unique=True,
            postgresql_where=text("crm_user_id IS NOT NULL"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    external_role_label: Mapped[str] = mapped_column(String(64), nullable=False, default="admin")
    lms_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    crm_user_id: Mapped[str | None] = mapped_column(String(24), nullable=True)

    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")


class ApiKey(UUIDMixin, TimestampMixin, Base):
    """Per-tenant API key. Only the hash is stored; the prefix aids lookup."""

    __tablename__ = "api_keys"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(16), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    scopes: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuditLog(UUIDMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
