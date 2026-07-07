"""Auth dependencies: resolve RequestContext and enforce permissions.

Resolution order:
1. ``X-API-Key`` -> tenant service account (LMS/CRM backends).
2. ``Authorization: Bearer`` platform JWT -> tenant admin / operator.
3. Product user JWT (LMS/CRM secret) -> end-user claims; tenant from API key or ``org_id``.
4. No credentials -> anonymous dev context when enabled, else 401.

Optional headers (``X-Product``, ``X-Agent``, ``X-Session-Id``, ``X-Acting-User-Id``)
refine routing after auth succeeds.
"""
from __future__ import annotations

import hmac
import uuid

from fastapi import Depends, HTTPException, Request

from app.config import settings
from app.modules.identity import repository
from app.modules.identity.models import User
from app.platform.auth import api_keys as api_key_utils
from app.platform.auth import jwt as jwt_auth
from app.platform.auth import product_jwt
from app.platform.auth import rbac
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability import tracing
from app.platform.observability.logging import get_logger
from app.platform.tenancy.constants import KNOWN_PRODUCTS, AuthMode
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.request_context import RequestContext

logger = get_logger(__name__)


def _header_product(request: Request) -> str | None:
    raw = (request.headers.get("X-Product") or "").strip().lower()
    return raw if raw in KNOWN_PRODUCTS else None


async def _ctx_from_api_key(full_key: str) -> TenantContext | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        record = await repository.get_api_key_by_prefix(
            session, api_key_utils.key_prefix(full_key)
        )
        if record is None or record.revoked:
            return None
        if not api_key_utils.verify_key(full_key, record.key_hash):
            return None
        tenant = await repository.get_tenant(session, record.tenant_id)
        if tenant is None or tenant.status != "active":
            return None
        await repository.touch_api_key_last_used(session, record)
        await session.commit()
        scopes = list(record.scopes) if record.scopes else list(rbac.DEFAULT_API_KEY_SCOPES)
        return TenantContext(
            tenant_id=str(record.tenant_id),
            plan=tenant.plan,
            budget=tenant.budget_monthly,
            priority=tenant.priority,
            scopes=scopes,
            user_id=None,
            is_authenticated=True,
        )


async def _ctx_from_platform_jwt(token: str) -> TenantContext | None:
    try:
        claims = jwt_auth.decode_token(token)
    except jwt_auth.InvalidToken:
        return None
    if claims.get("type") != "access":
        return None

    tid = str(claims.get("tid", ""))
    sub = claims.get("sub")
    try:
        sessionmaker = get_sessionmaker()
        async with sessionmaker() as session:
            tenant = await repository.get_tenant(session, uuid.UUID(tid)) if tid else None
            if tenant is None or tenant.status != "active":
                return None
            if sub:
                user = await session.get(User, uuid.UUID(sub))
                if user is None or user.status != "active":
                    return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("JWT caller validation failed: %s", exc)
        return None

    return TenantContext(
        tenant_id=tid,
        plan=claims.get("plan", "free"),
        roles=list(claims.get("roles", [])),
        scopes=list(claims.get("scopes", [])),
        user_id=sub,
        is_authenticated=True,
    )


async def _tenant_from_org_id(org_id: str) -> TenantContext | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        tenant = await repository.get_tenant_by_org_identifier(session, org_id)
        if tenant is None or tenant.status != "active":
            direct = product_jwt.org_id_as_tenant_uuid(org_id)
            if direct is not None:
                tenant = await repository.get_tenant(session, direct)
        if tenant is None or tenant.status != "active":
            return None
        return TenantContext(
            tenant_id=str(tenant.id),
            plan=tenant.plan,
            budget=tenant.budget_monthly,
            priority=tenant.priority,
            scopes=list(rbac.DEFAULT_API_KEY_SCOPES),
            is_authenticated=True,
        )


def _try_decode_product_token(
    token: str, header_product: str | None
) -> tuple[dict, str] | None:
    products = [header_product] if header_product in KNOWN_PRODUCTS else list(KNOWN_PRODUCTS)
    for product in products:
        try:
            claims = product_jwt.decode_product_token(token, product)
            resolved = product_jwt.claims_product(claims, header_product) or product
            if resolved in KNOWN_PRODUCTS:
                return claims, resolved
        except product_jwt.InvalidProductToken:
            continue
    return None


def _bind_tracing(ctx: RequestContext) -> None:
    tracing.bind_request_context(
        tenant_id=ctx.tenant_id,
        user_id=ctx.acting_user_id or ctx.user_id or ctx.external_user_id,
        product=ctx.product,
        agent=ctx.agent,
        session_id=ctx.session_id,
        acting_user_id=ctx.acting_user_id,
        auth_mode=ctx.auth_mode,
    )


async def get_request_context(request: Request) -> RequestContext:
    api_key = request.headers.get("X-API-Key")
    authorization = request.headers.get("Authorization", "")
    bearer = authorization[len("Bearer ") :].strip() if authorization.startswith("Bearer ") else None
    header_product = _header_product(request)

    ctx: RequestContext | None = None
    credentials_provided = bool(api_key) or bool(bearer)

    if api_key:
        tenant = await _ctx_from_api_key(api_key)
        if tenant is not None:
            ctx = RequestContext.from_tenant(tenant, auth_mode=AuthMode.API_KEY)

    if bearer and ctx is None:
        tenant = await _ctx_from_platform_jwt(bearer)
        if tenant is not None:
            ctx = RequestContext.from_tenant(tenant, auth_mode=AuthMode.PLATFORM_JWT)

    product_decoded: tuple[dict, str] | None = None
    if bearer:
        if ctx is None or api_key:
            product_decoded = _try_decode_product_token(bearer, header_product)

    if product_decoded is not None:
        claims, product = product_decoded
        org_id = product_jwt.claims_org_id(claims)
        user_id = product_jwt.claims_user_id(claims)
        roles = product_jwt.claims_roles(claims)

        if ctx is None:
            if not org_id:
                raise HTTPException(
                    status_code=401, detail="Product token missing org_id for tenant resolution"
                )
            tenant = await _tenant_from_org_id(org_id)
            if tenant is None:
                raise HTTPException(status_code=401, detail="Invalid credentials")
            ctx = RequestContext.from_tenant(tenant, auth_mode=AuthMode.PRODUCT_USER_JWT)
            ctx.enrich_product_user(
                product=product,
                external_user_id=user_id or "",
                product_roles=roles,
                org_id=org_id,
            )
        else:
            ctx.enrich_product_user(
                product=product,
                external_user_id=user_id or "",
                product_roles=roles,
                org_id=org_id,
            )

    if ctx is None:
        if credentials_provided:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if settings.auth_allow_anonymous:
            ctx = RequestContext.anonymous()
        else:
            raise HTTPException(status_code=401, detail="Authentication required")

    ctx.apply_headers(request)
    _bind_tracing(ctx)
    return ctx


async def get_tenant_context(
    ctx: RequestContext = Depends(get_request_context),
) -> TenantContext:
    """Backward-compatible alias — returns the same ``RequestContext`` instance."""
    return ctx


def require_permission(permission: str):
    """Build a dependency that 403s unless the context holds ``permission``."""

    async def _dependency(
        ctx: RequestContext = Depends(get_request_context),
    ) -> RequestContext:
        if not ctx.has(permission):
            raise HTTPException(status_code=403, detail=f"Missing permission: {permission}")
        return ctx

    return _dependency


async def verify_provisioning_key(request: Request) -> None:
    """Gate purchase-time provisioning on ``X-Provisioning-Key``."""
    expected = settings.provisioning_api_key
    if not expected:
        raise HTTPException(status_code=404, detail="Provisioning endpoint is disabled")
    provided = request.headers.get("X-Provisioning-Key", "")
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid provisioning key")
