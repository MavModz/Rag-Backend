"""Identity data access (async SQLAlchemy). Thin queries, no business rules."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
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


async def get_tenant_by_external_org_id(session: AsyncSession, org_id: str) -> Tenant | None:
    res = await session.execute(select(Tenant).where(Tenant.external_org_id == org_id))
    return res.scalar_one_or_none()


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
