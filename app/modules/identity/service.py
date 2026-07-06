"""Identity service: authentication, token issuance, tenant/user/key management.

Business logic only — no HTTP, no raw SQL (delegates to the repository).
"""
from __future__ import annotations

import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.modules.identity import repository
from app.modules.knowledge import repository as kb_repo
from app.modules.identity.models import ApiKey, Tenant, User
from app.platform.auth import api_keys as api_key_utils
from app.platform.auth import jwt as jwt_auth
from app.platform.auth import rbac
from app.platform.auth.password import hash_password, verify_password


class AuthError(Exception):
    pass


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return slug or "workspace"


async def _unique_slug(session: AsyncSession, base: str) -> str:
    slug, n = base, 1
    while await repository.get_tenant_by_slug(session, slug) is not None:
        n += 1
        slug = f"{base}-{n}"
    return slug


async def authenticate(
    session: AsyncSession, email: str, password: str
) -> tuple[User, list[str]]:
    user = await repository.get_user_by_email_any_tenant(session, email)
    if user is None or not user.password_hash or not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")
    if user.status != "active":
        raise AuthError("User is not active")
    scopes = rbac.expand_scopes([role.permissions for role in user.roles])
    return user, scopes


async def issue_tokens(session: AsyncSession, user: User, scopes: list[str]) -> dict:
    tenant = await repository.get_tenant(session, user.tenant_id)
    plan = tenant.plan if tenant else "free"
    roles = [r.name for r in user.roles]
    access = jwt_auth.create_access_token(
        sub=str(user.id), tid=str(user.tenant_id), plan=plan, roles=roles, scopes=scopes
    )
    refresh = jwt_auth.create_refresh_token(sub=str(user.id), tid=str(user.tenant_id))
    return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> dict:
    try:
        claims = jwt_auth.decode_token(refresh_token)
    except jwt_auth.InvalidToken as exc:
        raise AuthError("Invalid refresh token") from exc
    if claims.get("type") != "refresh":
        raise AuthError("Not a refresh token")
    user = await session.get(User, uuid.UUID(claims["sub"]))
    if user is None or user.status != "active":
        raise AuthError("User no longer valid")
    scopes = rbac.expand_scopes([role.permissions for role in user.roles])
    return await issue_tokens(session, user, scopes)


async def create_tenant(session: AsyncSession, *, name: str, slug: str, plan: str) -> Tenant:
    tenant = Tenant(name=name, slug=slug, plan=plan)
    await repository.add(session, tenant)
    return tenant


async def create_user(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    password: str,
    name: str | None = None,
    phone: str | None = None,
    role_names: list[str],
) -> User:
    roles = await repository.get_roles_by_names(session, role_names)
    user = User(
        tenant_id=tenant_id,
        email=email,
        phone=phone,
        name=name,
        password_hash=hash_password(password),
        roles=roles,
    )
    await repository.add(session, user)
    return user


async def create_api_key(
    session: AsyncSession, *, tenant_id: uuid.UUID, name: str, scopes: list[str]
) -> tuple[ApiKey, str]:
    full_key, prefix, key_hash = api_key_utils.generate_api_key()
    record = ApiKey(
        tenant_id=tenant_id,
        name=name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=scopes or list(rbac.DEFAULT_API_KEY_SCOPES),
    )
    await repository.add(session, record)
    return record, full_key


async def register_workspace(
    session: AsyncSession,
    *,
    workspace_name: str,
    email: str,
    password: str,
    slug: str | None = None,
    plan: str | None = None,
) -> dict:
    """Provision a new workspace: tenant + admin user + starter API key.

    Shared by public self-serve registration, superadmin bulk provisioning, and
    the purchase-time provisioning endpoint. Raises AuthError on duplicate email.
    Returns auto-login tokens + the API key (shown once).
    """
    if await repository.get_user_by_email_any_tenant(session, email) is not None:
        raise AuthError("A user with this email already exists")

    final_slug = await _unique_slug(session, slugify(slug or workspace_name))
    tenant = await create_tenant(
        session, name=workspace_name, slug=final_slug, plan=plan or settings.default_signup_plan
    )
    user = await create_user(
        session,
        tenant_id=tenant.id,
        email=email,
        password=password,
        name=workspace_name,  # auto-provisioned admin named after the workspace
        phone=None,
        role_names=["admin"],
    )
    record, full_key = await create_api_key(
        session, tenant_id=tenant.id, name="default", scopes=list(rbac.DEFAULT_API_KEY_SCOPES)
    )
    await kb_repo.ensure_default_knowledge_bases(session, tenant.id)
    scopes = rbac.expand_scopes([r.permissions for r in user.roles])
    tokens = await issue_tokens(session, user, scopes)
    return {
        "tenant_id": str(tenant.id),
        "tenant_slug": tenant.slug,
        "api_key": full_key,
        "api_key_prefix": record.prefix,
        **tokens,
    }
