"""Provisioning router (/provisioning): cross-product user onboarding.

Gated by the shared-secret ``verify_provisioning_key`` dependency. Creates or
updates users keyed by admin_email + phone + role, merging LMS/CRM identifiers.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.admin import schemas as admin_schemas
from app.modules.provisioning import schemas
from app.modules.provisioning import service as provisioning_service
from app.platform.auth.dependencies import verify_provisioning_key
from app.platform.db.postgres import get_session

router = APIRouter(prefix="/provisioning", tags=["provisioning"])


@router.post(
    "/tenants",
    response_model=schemas.ProvisionTenantResponse,
    status_code=200,
    dependencies=[Depends(verify_provisioning_key)],
)
async def provision_tenant(
    payload: schemas.ProvisionTenantRequest,
    session: AsyncSession = Depends(get_session),
) -> schemas.ProvisionTenantResponse:
    row = admin_schemas.ProvisionRow(
        name=payload.name,
        company_name=payload.company_name,
        plan=payload.plan,
        admin_email=payload.admin_email,
        admin_password=payload.admin_password,
        phone=payload.phone,
        role=payload.role,
        lms_user_id=payload.lms_user_id,
        lms_institute_id=payload.lms_institute_id,
        crm_user_id=payload.crm_user_id,
        crm_company_id=payload.crm_company_id,
    )
    try:
        result = await provisioning_service.upsert_provisioned_user(
            session, row, require_platform_ids=True
        )
        await session.commit()
    except provisioning_service.ProvisioningError as exc:
        await session.rollback()
        status = 409 if exc.code.endswith("_CONFLICT") else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc

    if result.status == "error":
        raise HTTPException(status_code=409, detail=result.error or "Could not provision tenant")

    return schemas.ProvisionTenantResponse(
        tenant_id=result.tenant_id or "",
        api_key=result.api_key,
        operation=result.status,
    )
