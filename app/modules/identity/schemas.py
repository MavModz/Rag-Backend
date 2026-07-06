"""Identity request/response models."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    workspace_name: str = Field(..., max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8)
    slug: str | None = None


class RegisterResponse(BaseModel):
    tenant_id: str
    tenant_slug: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    api_key: str = Field(..., description="Tenant API key for server-to-server calls — shown once.")
    api_key_prefix: str


class WhoAmI(BaseModel):
    tenant_id: str
    user_id: str | None = None
    plan: str
    scopes: list[str]
    authenticated: bool


class ApiKeyCreate(BaseModel):
    name: str = Field(..., max_length=128)
    scopes: list[str] = Field(default_factory=list)


class ApiKeyCreated(BaseModel):
    id: str
    name: str
    prefix: str
    api_key: str = Field(..., description="Shown once — store it now; only the hash is kept.")
    scopes: list[str]


class TenantCreate(BaseModel):
    name: str
    slug: str
    plan: str = "free"


class TenantOut(BaseModel):
    id: str
    name: str
    slug: str
    plan: str


class UserCreate(BaseModel):
    name: str
    phone: str
    email: EmailStr
    password: str
    roles: list[str] = Field(default_factory=lambda: ["member"])


class UserOut(BaseModel):
    id: str
    name: str | None = None
    phone: str | None = None
    # Lenient on output (see admin.schemas.UserOut); input is validated via UserCreate.
    email: str
    roles: list[str]
