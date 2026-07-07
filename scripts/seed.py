"""Seed the platform database with baseline rows (idempotent).

Run after ``alembic upgrade head``:

    python -m scripts.seed

Seeds: a default tenant, the baseline RBAC roles, a default Mongo data-source
(reproducing today's WhatsApp read behavior), the Ollama model-registry profiles,
and the default system prompt template. Phase 6 extends this with an admin user
and a tenant API key once the auth utilities exist. Safe to run repeatedly — each
row is created only if absent.
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from sqlalchemy import func

from app.config import settings
from app.jobs import models as _jobs  # noqa: F401 - register metadata
from app.modules.identity.models import ApiKey, Role, Tenant, User
from app.modules.knowledge import repository as kb_repo
from app.modules.model_gateway.models import ModelRegistry, PromptTemplate
from app.platform.auth.api_keys import generate_api_key
from app.platform.auth.password import hash_password
from app.platform.db.postgres import get_sessionmaker
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

DEFAULT_TENANT_SLUG = "default"

# Baseline roles. A flat permission list; "*" grants everything (admin).
ROLES = {
    "admin": ["*"],
    "member": ["chat:write", "kb:read", "kb:write", "usage:read", "datasources:manage"],
    "viewer": ["chat:write", "kb:read"],
}

SYSTEM_PROMPT = (
    "You are a helpful customer support assistant for a company. "
    "Answer the user's question using ONLY the provided knowledge base context "
    "and the prior conversation. "
    "If the answer is not contained in the context, say you don't have that "
    "information and offer to connect them with a human agent. "
    "Be concise, friendly, and never invent facts or policies."
)


async def _seed() -> None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        # --- Default tenant ---
        tenant = (
            await session.execute(
                select(Tenant).where(Tenant.slug == DEFAULT_TENANT_SLUG)
            )
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="Default Tenant",
                slug=DEFAULT_TENANT_SLUG,
                plan="enterprise",
                status="active",
                priority=10,
            )
            session.add(tenant)
            await session.flush()
            logger.info("Seeded default tenant %s", tenant.id)

        await kb_repo.ensure_default_knowledge_bases(session, tenant.id)
        logger.info("Ensured default knowledge bases for tenant %s", tenant.id)

        # --- Roles ---
        for name, perms in ROLES.items():
            existing = (
                await session.execute(select(Role).where(Role.name == name))
            ).scalar_one_or_none()
            if existing is None:
                session.add(Role(name=name, permissions=perms, description=f"{name} role"))
                logger.info("Seeded role %s", name)
        await session.flush()

        # --- Admin user (default tenant) ---
        admin = (
            await session.execute(
                select(User).where(
                    User.tenant_id == tenant.id, User.email == settings.seed_admin_email
                )
            )
        ).scalar_one_or_none()
        if admin is None:
            admin_role = (
                await session.execute(select(Role).where(Role.name == "admin"))
            ).scalar_one()
            session.add(
                User(
                    tenant_id=tenant.id,
                    email=settings.seed_admin_email,
                    password_hash=hash_password(settings.seed_admin_password),
                    name="Platform Admin",
                    phone=None,
                    external_role_label="admin",
                    roles=[admin_role],
                )
            )
            logger.info("Seeded admin user %s", settings.seed_admin_email)

        # --- Bootstrap API key (only when the tenant has none) ---
        key_count = (
            await session.execute(
                select(func.count()).select_from(ApiKey).where(ApiKey.tenant_id == tenant.id)
            )
        ).scalar_one()
        if key_count == 0:
            full_key, prefix, key_hash = generate_api_key()
            session.add(
                ApiKey(
                    tenant_id=tenant.id,
                    name="bootstrap",
                    prefix=prefix,
                    key_hash=key_hash,
                    scopes=["*"],
                )
            )
            logger.info("Seeded bootstrap API key (shown once below)")
            print("\n=== BOOTSTRAP API KEY (store now; not recoverable) ===")
            print(full_key)
            print("======================================================\n")

        # No data source is seeded: the platform is DB-independent. Each tenant
        # registers their own database via the /data-sources API / admin UI.

        # --- Model registry (Ollama profiles) ---
        profiles = {
            "conversation.default": ModelRegistry(
                profile_name="conversation.default",
                provider="ollama",
                model=settings.ollama_chat_model,
                params={
                    "temperature": settings.ollama_temperature,
                    "num_predict": settings.ollama_num_predict,
                },
            ),
            "embedding.default": ModelRegistry(
                profile_name="embedding.default",
                provider="ollama",
                model=settings.ollama_embed_model,
                params={},
            ),
        }
        for name, row in profiles.items():
            existing = (
                await session.execute(
                    select(ModelRegistry).where(ModelRegistry.profile_name == name)
                )
            ).scalar_one_or_none()
            if existing is None:
                session.add(row)
                logger.info("Seeded model profile %s", name)

        # --- Default system prompt template (global) ---
        pt = (
            await session.execute(
                select(PromptTemplate).where(
                    PromptTemplate.key == "conversation.system",
                    PromptTemplate.tenant_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        if pt is None:
            session.add(
                PromptTemplate(
                    tenant_id=None, key="conversation.system", version=1, body=SYSTEM_PROMPT
                )
            )
            logger.info("Seeded default system prompt template")

        await session.commit()
    logger.info("Seed complete.")


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
