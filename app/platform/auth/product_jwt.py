"""LMS/CRM end-user JWT validation (separate secrets from platform JWT)."""
from __future__ import annotations

import uuid

from jose import JWTError, jwt

from app.config import settings
from app.platform.tenancy.constants import KNOWN_PRODUCTS, PRODUCT_CRM, PRODUCT_LMS


class InvalidProductToken(Exception):
    pass


def product_jwt_secret(product: str) -> str | None:
    if product == PRODUCT_LMS:
        return settings.lms_jwt_secret or None
    if product == PRODUCT_CRM:
        return settings.crm_jwt_secret or None
    return None


def decode_product_token(token: str, product: str) -> dict:
    """Decode a product-issued user JWT. ``product`` must be ``lms`` or ``crm``."""
    if product not in KNOWN_PRODUCTS:
        raise InvalidProductToken(f"Unknown product: {product!r}")
    secret = product_jwt_secret(product)
    if not secret:
        raise InvalidProductToken(f"JWT secret not configured for product {product!r}")
    try:
        return jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise InvalidProductToken(str(exc)) from exc


def claims_org_id(claims: dict) -> str | None:
    for key in ("org_id", "organization_id", "tenant_id", "tid"):
        value = claims.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def claims_product(claims: dict, header_product: str | None) -> str | None:
    raw = claims.get("product") or claims.get("iss") or header_product
    if not raw:
        return None
    slug = str(raw).strip().lower()
    return slug if slug in KNOWN_PRODUCTS else None


def claims_user_id(claims: dict) -> str | None:
    sub = claims.get("sub")
    return str(sub).strip() if sub is not None else None


def claims_roles(claims: dict) -> list[str]:
    roles = claims.get("roles") or claims.get("role") or []
    if isinstance(roles, str):
        return [roles]
    return [str(r) for r in roles]


def org_id_as_tenant_uuid(org_id: str) -> uuid.UUID | None:
    """Allow org_id to be the platform tenant UUID directly."""
    try:
        return uuid.UUID(org_id)
    except (ValueError, TypeError, AttributeError):
        return None
