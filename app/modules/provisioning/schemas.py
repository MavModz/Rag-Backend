"""Provisioning request/response models."""
from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

_OBJECT_ID_RE = re.compile(r"^[a-f0-9]{24}$")


class ProvisionTenantRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    company_name: str = Field(..., min_length=1, max_length=255)
    admin_email: EmailStr
    phone: str = Field(..., min_length=1, max_length=32)
    role: str = Field(..., min_length=1, max_length=64)
    plan: str | None = None
    admin_password: str | None = Field(
        default=None,
        description="Ignored for cross-platform provisioning; users authenticate via product JWT + API key.",
    )
    lms_user_id: int | None = None
    lms_institute_id: int | None = None
    crm_user_id: str | None = None
    crm_company_id: str | None = None

    @field_validator("phone")
    @classmethod
    def strip_phone(cls, value: str) -> str:
        return re.sub(r"\s+", "", value.strip())

    @field_validator("role")
    @classmethod
    def strip_role(cls, value: str) -> str:
        return value.strip()

    @field_validator("crm_user_id", "crm_company_id")
    @classmethod
    def validate_object_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not _OBJECT_ID_RE.match(cleaned):
            raise ValueError("must be a 24-char hex ObjectId")
        return cleaned

    @field_validator("lms_user_id", "lms_institute_id")
    @classmethod
    def validate_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("must be a positive integer")
        return value

    @model_validator(mode="after")
    def require_platform_ids(self) -> ProvisionTenantRequest:
        if all(
            value is None
            for value in (
                self.lms_user_id,
                self.lms_institute_id,
                self.crm_user_id,
                self.crm_company_id,
            )
        ):
            raise ValueError("at least one platform identifier is required")
        return self


class ProvisionTenantResponse(BaseModel):
    tenant_id: str
    api_key: str | None = Field(
        default=None,
        description="Shown once on create; omitted on update because only the hash is stored.",
    )
    operation: str = Field(description="created or updated")
