"""Provisioning request/response models."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr


class ProvisionTenantRequest(BaseModel):
    name: str
    plan: str | None = None
    admin_email: EmailStr
    admin_password: str | None = None  # generated if absent


class ProvisionTenantResponse(BaseModel):
    tenant_id: str
    admin_email: str
    admin_password: str | None = None  # generated only; shown once
    api_key: str                        # shown once
