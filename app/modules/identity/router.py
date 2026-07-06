"""Identity router: auth (login/refresh/whoami) + tenant/user/API-key admin.

Request/response only; all logic is in the service. Admin routes require the
relevant permission via ``require_permission``.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.identity import schemas, service
from app.platform.auth import rbac
from app.platform.auth.dependencies import get_tenant_context, require_permission
from app.platform.db.postgres import get_session
from app.platform.ratelimit.limiter import limiter
from app.platform.tenancy.context import TenantContext

router = APIRouter(prefix="/auth", tags=["identity"])


@router.post("/register", response_model=schemas.RegisterResponse, status_code=201)
@limiter.limit("5/minute")
async def register(
    request: Request,
    payload: schemas.RegisterRequest,
    session: AsyncSession = Depends(get_session),
) -> schemas.RegisterResponse:
    """Public self-serve signup (standalone purchasers): create a workspace.

    Creates a tenant + admin user + starter API key and auto-logs in. Disabled
    when ALLOW_PUBLIC_REGISTRATION is false.
    """
    if not settings.allow_public_registration:
        raise HTTPException(status_code=403, detail="Public registration is disabled")
    try:
        result = await service.register_workspace(
            session,
            workspace_name=payload.workspace_name,
            email=payload.email,
            password=payload.password,
            slug=payload.slug,
        )
    except service.AuthError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return schemas.RegisterResponse(**result)


@router.post("/login", response_model=schemas.TokenResponse)
async def login(
    payload: schemas.LoginRequest, session: AsyncSession = Depends(get_session)
) -> schemas.TokenResponse:
    try:
        user, scopes = await service.authenticate(session, payload.email, payload.password)
        tokens = await service.issue_tokens(session, user, scopes)
    except service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return schemas.TokenResponse(**tokens)


@router.post("/refresh", response_model=schemas.TokenResponse)
async def refresh(
    payload: schemas.RefreshRequest, session: AsyncSession = Depends(get_session)
) -> schemas.TokenResponse:
    try:
        tokens = await service.refresh_tokens(session, payload.refresh_token)
    except service.AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return schemas.TokenResponse(**tokens)


@router.get("/whoami", response_model=schemas.WhoAmI)
async def whoami(ctx: TenantContext = Depends(get_tenant_context)) -> schemas.WhoAmI:
    return schemas.WhoAmI(
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        plan=ctx.plan,
        scopes=ctx.scopes,
        authenticated=ctx.is_authenticated,
    )


@router.post("/tenants", response_model=schemas.TenantOut, status_code=201)
async def create_tenant(
    payload: schemas.TenantCreate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.TenantOut:
    tenant = await service.create_tenant(
        session, name=payload.name, slug=payload.slug, plan=payload.plan
    )
    return schemas.TenantOut(
        id=str(tenant.id), name=tenant.name, slug=tenant.slug, plan=tenant.plan
    )


@router.post("/users", response_model=schemas.UserOut, status_code=201)
async def create_user(
    payload: schemas.UserCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_USERS)),
) -> schemas.UserOut:
    user = await service.create_user(
        session,
        tenant_id=uuid.UUID(ctx.tenant_id),
        email=payload.email,
        password=payload.password,
        name=payload.name,
        phone=payload.phone,
        role_names=payload.roles,
    )
    return schemas.UserOut(
        id=str(user.id),
        name=user.name,
        phone=user.phone,
        email=user.email,
        roles=[r.name for r in user.roles],
    )


@router.post("/api-keys", response_model=schemas.ApiKeyCreated, status_code=201)
async def create_api_key(
    payload: schemas.ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_KEYS)),
) -> schemas.ApiKeyCreated:
    record, full_key = await service.create_api_key(
        session, tenant_id=uuid.UUID(ctx.tenant_id), name=payload.name, scopes=payload.scopes
    )
    return schemas.ApiKeyCreated(
        id=str(record.id),
        name=record.name,
        prefix=record.prefix,
        api_key=full_key,
        scopes=record.scopes,
    )
