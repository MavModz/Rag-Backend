"""Data Sources router (/data-sources): tenant self-service.

Operates on the *caller's own tenant* (from the tenant context). Every route is
gated on ``datasources:manage``. Requires an authenticated, UUID-keyed tenant —
the anonymous/dev context has no tenant to attach sources to.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.datasources import repository as repo
from app.modules.datasources import schemas, service
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.db.postgres import get_session
from app.platform.tenancy.context import TenantContext

router = APIRouter(prefix="/data-sources", tags=["data-sources"])

_GATE = require_permission(Permission.DATASOURCES_MANAGE)


def _tenant_id(ctx: TenantContext) -> uuid.UUID:
    tid = ctx.tenant_uuid()
    if tid is None:
        raise HTTPException(
            status_code=400,
            detail="Managing data sources requires an authenticated tenant (log in).",
        )
    return tid


@router.get("", response_model=list[schemas.DataSourceOut])
async def list_data_sources(
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(_GATE),
) -> list[schemas.DataSourceOut]:
    rows = await repo.list_for_tenant(session, _tenant_id(ctx))
    return [service.to_out(r) for r in rows]


@router.post("", response_model=schemas.DataSourceOut, status_code=201)
async def create_data_source(
    payload: schemas.DataSourceCreate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(_GATE),
) -> schemas.DataSourceOut:
    src = await service.create(session, _tenant_id(ctx), payload)
    return service.to_out(src)


@router.post("/test", response_model=schemas.TestResult)
async def test_data_source(
    payload: schemas.TestRequest,
    ctx: TenantContext = Depends(_GATE),
) -> schemas.TestResult:
    return await service.test_connection(payload)


@router.post("/discover", response_model=schemas.DiscoverResult)
async def discover_data_source(
    payload: schemas.DiscoverRequest,
    ctx: TenantContext = Depends(_GATE),
) -> schemas.DiscoverResult:
    try:
        return await service.discover(payload)
    except Exception as exc:  # noqa: BLE001 - surface discovery errors as 400
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{source_id}", response_model=schemas.DataSourceOut)
async def get_data_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(_GATE),
) -> schemas.DataSourceOut:
    src = await repo.get_for_tenant(session, _tenant_id(ctx), _as_uuid(source_id))
    if src is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    return service.to_out(src)


@router.patch("/{source_id}", response_model=schemas.DataSourceOut)
async def update_data_source(
    source_id: str,
    payload: schemas.DataSourceUpdate,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(_GATE),
) -> schemas.DataSourceOut:
    src = await repo.get_for_tenant(session, _tenant_id(ctx), _as_uuid(source_id))
    if src is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    src = await service.update(session, src, payload)
    return service.to_out(src)


@router.delete("/{source_id}", status_code=204)
async def delete_data_source(
    source_id: str,
    session: AsyncSession = Depends(get_session),
    ctx: TenantContext = Depends(_GATE),
) -> None:
    src = await repo.get_for_tenant(session, _tenant_id(ctx), _as_uuid(source_id))
    if src is None:
        raise HTTPException(status_code=404, detail="Data source not found")
    await service.delete_source(session, src)


def _as_uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid data source id") from None
