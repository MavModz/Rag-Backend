"""Admin request/response models (read-heavy, paginated)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class Page(BaseModel):
    total: int
    limit: int
    offset: int


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    status: str
    budget_monthly: float
    priority: int
    created_at: datetime
    user_count: int = 0
    api_key_count: int = 0


class TenantList(Page):
    items: list[TenantOut]


class TenantUpdate(BaseModel):
    plan: str | None = None
    status: str | None = None
    budget_monthly: float | None = None
    priority: int | None = None


class UserOut(BaseModel):
    id: str
    tenant_id: str
    name: str | None
    phone: str | None
    # Lenient on output: stored emails (incl. legacy/reserved domains) must never
    # break serialization. Email format is validated on input (UserCreate).
    email: str
    status: str
    roles: list[str]
    created_at: datetime


class UserList(Page):
    items: list[UserOut]


class UserUpdate(BaseModel):
    status: str | None = None
    roles: list[str] | None = None


class ApiKeyOut(BaseModel):
    id: str
    name: str
    prefix: str
    scopes: list[str]
    revoked: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyList(Page):
    items: list[ApiKeyOut]


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=128)
    scopes: list[str] = Field(default_factory=list)


class ApiKeyCreated(ApiKeyOut):
    api_key: str = Field(..., description="Shown once — store it now.")


class RoleOut(BaseModel):
    id: str
    name: str
    permissions: list[str]


# ---- Bulk onboarding / provisioning ----
class ProvisionRow(BaseModel):
    name: str
    company_name: str | None = None
    slug: str | None = None
    plan: str | None = None
    admin_email: EmailStr
    admin_password: str | None = None  # generated if absent (legacy bulk only)
    phone: str | None = None
    role: str | None = None
    lms_user_id: int | None = None
    lms_institute_id: int | None = None
    crm_user_id: str | None = None
    crm_company_id: str | None = None
    # Optional: attach the client's existing database in the same step.
    ds_type: str | None = None         # mongo | sql | mysql | postgres
    ds_conn: str | None = None         # connection string
    ds_db: str | None = None
    ds_collections: str | None = None  # comma-separated (CSV-friendly)
    ds_table: str | None = None
    ds_field_mapping: dict | None = None


class BulkProvisionRequest(BaseModel):
    rows: list[ProvisionRow]


class ProvisionResult(BaseModel):
    name: str
    status: str  # created | updated | skipped | error
    tenant_id: str | None = None
    admin_email: str | None = None
    admin_password: str | None = None  # generated only; shown once
    api_key: str | None = None         # shown once on create
    api_key_prefix: str | None = None
    data_source_id: str | None = None
    error: str | None = None


class BulkProvisionResponse(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: int
    results: list[ProvisionResult]
