"""Identity data access (async SQLAlchemy). Thin queries, no business rules."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import ApiKey, Role, Tenant, User


async def get_user_by_email(session: AsyncSession, tenant_id: uuid.UUID, email: str) -> User | None:
    res = await session.execute(
        select(User).where(User.tenant_id == tenant_id, User.email == email)
    )
    return res.scalar_one_or_none()


async def get_user_by_email_any_tenant(session: AsyncSession, email: str) -> User | None:
    res = await session.execute(select(User).where(User.email == email))
    return res.scalars().first()


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


async def get_tenant_by_slug(session: AsyncSession, slug: str) -> Tenant | None:
    res = await session.execute(select(Tenant).where(Tenant.slug == slug))
    return res.scalar_one_or_none()


async def get_tenant_by_lms_institute_id(session: AsyncSession, institute_id: int) -> Tenant | None:
    res = await session.execute(select(Tenant).where(Tenant.lms_institute_id == institute_id))
    return res.scalar_one_or_none()


async def get_tenant_by_crm_company_id(session: AsyncSession, company_id: str) -> Tenant | None:
    res = await session.execute(select(Tenant).where(Tenant.crm_company_id == company_id))
    return res.scalar_one_or_none()


async def get_user_by_lms_user_id(session: AsyncSession, user_id: int) -> User | None:
    res = await session.execute(select(User).where(User.lms_user_id == user_id))
    return res.scalar_one_or_none()


async def get_user_by_crm_user_id(session: AsyncSession, user_id: str) -> User | None:
    res = await session.execute(select(User).where(User.crm_user_id == user_id))
    return res.scalar_one_or_none()


async def find_user_by_provisioning_identity(
    session: AsyncSession, email: str, phone: str, external_role_label: str
) -> User | None:
    res = await session.execute(
        select(User).where(
            func.lower(User.email) == email.lower(),
            User.phone == phone,
            User.external_role_label == external_role_label,
        )
    )
    return res.scalar_one_or_none()


async def get_default_api_key(session: AsyncSession, tenant_id: uuid.UUID) -> ApiKey | None:
    res = await session.execute(
        select(ApiKey)
        .where(
            ApiKey.tenant_id == tenant_id,
            ApiKey.name == "default",
            ApiKey.revoked.is_(False),
        )
        .order_by(ApiKey.created_at.asc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def get_tenant_by_org_identifier(session: AsyncSession, org_id: str) -> Tenant | None:
    """Resolve a tenant from LMS institute id or CRM company id."""
    if org_id.isdigit():
        tenant = await get_tenant_by_lms_institute_id(session, int(org_id))
        if tenant is not None:
            return tenant
    cleaned = org_id.strip().lower()
    if _OBJECT_ID_RE.match(cleaned):
        return await get_tenant_by_crm_company_id(session, cleaned)
    return None


_OBJECT_ID_RE = re.compile(r"^[a-f0-9]{24}$")


async def get_roles_by_names(session: AsyncSession, names: list[str]) -> list[Role]:
    if not names:
        return []
    res = await session.execute(select(Role).where(Role.name.in_(names)))
    return list(res.scalars().all())


async def get_api_key_by_prefix(session: AsyncSession, prefix: str) -> ApiKey | None:
    res = await session.execute(select(ApiKey).where(ApiKey.prefix == prefix))
    return res.scalar_one_or_none()


async def touch_api_key_last_used(session: AsyncSession, api_key: ApiKey) -> None:
    api_key.last_used_at = datetime.now(timezone.utc)


async def add(session: AsyncSession, obj) -> object:
    session.add(obj)
    await session.flush()
    return obj
