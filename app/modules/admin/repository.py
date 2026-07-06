"""Admin data access: cross-tenant reads + management mutations."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import ApiKey, Role, Tenant, User


# --- tenants ---
async def list_tenants(session: AsyncSession, limit: int, offset: int) -> tuple[list[Tenant], int]:
    total = (await session.execute(select(func.count()).select_from(Tenant))).scalar_one()
    rows = (
        await session.execute(
            select(Tenant).order_by(Tenant.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def count_users(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
    ).scalar_one()


async def count_api_keys(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    return (
        await session.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == tenant_id)
        )
    ).scalar_one()


async def get_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> Tenant | None:
    return await session.get(Tenant, tenant_id)


# --- users ---
async def list_users(
    session: AsyncSession, tenant_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[User], int]:
    total = (
        await session.execute(
            select(func.count()).select_from(User).where(User.tenant_id == tenant_id)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def get_user(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


# --- api keys ---
async def list_api_keys(
    session: AsyncSession, tenant_id: uuid.UUID, limit: int, offset: int
) -> tuple[list[ApiKey], int]:
    total = (
        await session.execute(
            select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == tenant_id)
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(ApiKey)
            .where(ApiKey.tenant_id == tenant_id)
            .order_by(ApiKey.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).scalars().all()
    return list(rows), total


async def get_api_key(session: AsyncSession, key_id: uuid.UUID) -> ApiKey | None:
    return await session.get(ApiKey, key_id)


# --- roles ---
async def list_roles(session: AsyncSession) -> list[Role]:
    return list((await session.execute(select(Role).order_by(Role.name))).scalars().all())
