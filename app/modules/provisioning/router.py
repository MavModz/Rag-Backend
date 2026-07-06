"""Provisioning router (/provisioning): purchase-time tenant creation.

Gated by the shared-secret ``verify_provisioning_key`` dependency. Reuses the
admin bulk-provision logic for a single tenant.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin import schemas as admin_schemas
from app.modules.admin import service as admin_service
from app.modules.provisioning import schemas
from app.platform.auth.dependencies import verify_provisioning_key
from app.platform.db.postgres import get_session

router = APIRouter(prefix="/provisioning", tags=["provisioning"])


@router.post(
    "/tenants",
    response_model=schemas.ProvisionTenantResponse,
    status_code=201,
    dependencies=[Depends(verify_provisioning_key)],
)
async def provision_tenant(
    payload: schemas.ProvisionTenantRequest,
    session: AsyncSession = Depends(get_session),
) -> schemas.ProvisionTenantResponse:
    row = admin_schemas.ProvisionRow(
        name=payload.name,
        plan=payload.plan,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
    )
    result = await admin_service.provision_one(session, row)
    await session.commit()
    if result.status != "created":
        raise HTTPException(status_code=409, detail=result.error or "Could not provision tenant")
    return schemas.ProvisionTenantResponse(
        tenant_id=result.tenant_id,
        admin_email=result.admin_email,
        admin_password=result.admin_password,
        api_key=result.api_key,
    )
