"""Admin router (/admin): cross-tenant management for the superadmin console.

Request/response only; queries/mutations delegate to the repository and reuse
``identity.service`` for creation logic. Every route is gated on an admin
permission; the seed admin (scopes ``["*"]``) is the platform superadmin.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin import repository as repo
from app.modules.admin import schemas
from app.modules.admin import service as admin_service
from app.modules.identity import repository as identity_repo
from app.modules.identity import schemas as identity_schemas
from app.modules.identity import service as identity_service
from app.platform.auth import rbac
from app.platform.auth.dependencies import require_permission
from app.platform.db.postgres import get_session
from app.platform.tenancy.context import TenantContext

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/provision", response_model=schemas.BulkProvisionResponse)
async def provision(
    payload: schemas.BulkProvisionRequest,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.BulkProvisionResponse:
    """Bulk-onboard tenants from a JSON list (+ optional data source per row)."""
    return await admin_service.provision_bulk(session, payload.rows)


@router.post("/provision/csv", response_model=schemas.BulkProvisionResponse)
async def provision_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.BulkProvisionResponse:
    """Bulk-onboard tenants from an uploaded CSV (columns: name, slug, plan,
    admin_email, admin_password, ds_type, ds_conn, ds_db, ds_collections, ds_table)."""
    content = await file.read()
    try:
        rows = admin_service.parse_csv(content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"Invalid CSV: {exc}") from exc
    return await admin_service.provision_bulk(session, rows)


def _tenant_out(t, *, user_count=0, api_key_count=0) -> schemas.TenantOut:
    return schemas.TenantOut(
        id=str(t.id), name=t.name, slug=t.slug, plan=t.plan, status=t.status,
        budget_monthly=t.budget_monthly, priority=t.priority, created_at=t.created_at,
        user_count=user_count, api_key_count=api_key_count,
    )


def _uuid(value: str, what: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Invalid {what} id") from None


def _user_out(u) -> schemas.UserOut:
    return schemas.UserOut(
        id=str(u.id), tenant_id=str(u.tenant_id), name=u.name, phone=u.phone,
        email=u.email, status=u.status, roles=[r.name for r in u.roles],
        created_at=u.created_at,
    )


# ------------------------------- tenants ---------------------------------
@router.get("/tenants", response_model=schemas.TenantList)
async def list_tenants(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.TenantList:
    tenants, total = await repo.list_tenants(session, limit, offset)
    items = [
        _tenant_out(
            t,
            user_count=await repo.count_users(session, t.id),
            api_key_count=await repo.count_api_keys(session, t.id),
        )
        for t in tenants
    ]
    return schemas.TenantList(items=items, total=total, limit=limit, offset=offset)


@router.post("/tenants", response_model=schemas.TenantOut, status_code=201)
async def create_tenant(
    payload: identity_schemas.TenantCreate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.TenantOut:
    tenant = await identity_service.create_tenant(
        session, name=payload.name, slug=payload.slug, plan=payload.plan
    )
    await session.flush()
    return _tenant_out(tenant)


@router.get("/tenants/{tenant_id}", response_model=schemas.TenantOut)
async def get_tenant(
    tenant_id: str,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.TenantOut:
    tid = _uuid(tenant_id, "tenant")
    tenant = await repo.get_tenant(session, tid)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return _tenant_out(
        tenant,
        user_count=await repo.count_users(session, tid),
        api_key_count=await repo.count_api_keys(session, tid),
    )


@router.patch("/tenants/{tenant_id}", response_model=schemas.TenantOut)
async def update_tenant(
    tenant_id: str,
    payload: schemas.TenantUpdate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_TENANTS)),
) -> schemas.TenantOut:
    tenant = await repo.get_tenant(session, _uuid(tenant_id, "tenant"))
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(tenant, field, value)
    return _tenant_out(tenant)


# -------------------------------- users ----------------------------------
@router.get("/tenants/{tenant_id}/users", response_model=schemas.UserList)
async def list_users(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_USERS)),
) -> schemas.UserList:
    tid = _uuid(tenant_id, "tenant")
    users, total = await repo.list_users(session, tid, limit, offset)
    items = [_user_out(u) for u in users]
    return schemas.UserList(items=items, total=total, limit=limit, offset=offset)


@router.post("/tenants/{tenant_id}/users", response_model=schemas.UserOut, status_code=201)
async def create_user(
    tenant_id: str,
    payload: identity_schemas.UserCreate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_USERS)),
) -> schemas.UserOut:
    tid = _uuid(tenant_id, "tenant")
    user = await identity_service.create_user(
        session, tenant_id=tid, email=payload.email, password=payload.password,
        name=payload.name, phone=payload.phone, role_names=payload.roles,
    )
    return _user_out(user)


@router.patch("/users/{user_id}", response_model=schemas.UserOut)
async def update_user(
    user_id: str,
    payload: schemas.UserUpdate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_USERS)),
) -> schemas.UserOut:
    user = await repo.get_user(session, _uuid(user_id, "user"))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.status is not None:
        user.status = payload.status
    if payload.roles is not None:
        user.roles = await identity_repo.get_roles_by_names(session, payload.roles)
    await session.flush()
    return _user_out(user)


# ------------------------------ api keys ---------------------------------
@router.get("/tenants/{tenant_id}/api-keys", response_model=schemas.ApiKeyList)
async def list_api_keys(
    tenant_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_KEYS)),
) -> schemas.ApiKeyList:
    tid = _uuid(tenant_id, "tenant")
    keys, total = await repo.list_api_keys(session, tid, limit, offset)
    items = [
        schemas.ApiKeyOut(
            id=str(k.id), name=k.name, prefix=k.prefix, scopes=k.scopes,
            revoked=k.revoked, last_used_at=k.last_used_at, created_at=k.created_at,
        )
        for k in keys
    ]
    return schemas.ApiKeyList(items=items, total=total, limit=limit, offset=offset)


@router.post("/tenants/{tenant_id}/api-keys", response_model=schemas.ApiKeyCreated, status_code=201)
async def create_api_key(
    tenant_id: str,
    payload: schemas.ApiKeyCreate,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_KEYS)),
) -> schemas.ApiKeyCreated:
    tid = _uuid(tenant_id, "tenant")
    record, full_key = await identity_service.create_api_key(
        session, tenant_id=tid, name=payload.name, scopes=payload.scopes
    )
    return schemas.ApiKeyCreated(
        id=str(record.id), name=record.name, prefix=record.prefix, scopes=record.scopes,
        revoked=record.revoked, last_used_at=record.last_used_at, created_at=record.created_at,
        api_key=full_key,
    )


@router.post("/api-keys/{key_id}/revoke", response_model=schemas.ApiKeyOut)
async def revoke_api_key(
    key_id: str,
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_KEYS)),
) -> schemas.ApiKeyOut:
    key = await repo.get_api_key(session, _uuid(key_id, "api key"))
    if key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    key.revoked = True
    await session.flush()
    return schemas.ApiKeyOut(
        id=str(key.id), name=key.name, prefix=key.prefix, scopes=key.scopes,
        revoked=key.revoked, last_used_at=key.last_used_at, created_at=key.created_at,
    )


# ------------------------------- roles -----------------------------------
@router.get("/roles", response_model=list[schemas.RoleOut])
async def list_roles(
    session: AsyncSession = Depends(get_session),
    _ctx: TenantContext = Depends(require_permission(rbac.Permission.ADMIN_USERS)),
) -> list[schemas.RoleOut]:
    roles = await repo.list_roles(session)
    return [
        schemas.RoleOut(id=str(r.id), name=r.name, permissions=r.permissions) for r in roles
    ]
