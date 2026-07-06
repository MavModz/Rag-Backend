"""Opt-in integration test against a real Postgres.

Skipped unless RUN_INTEGRATION=1 and POSTGRES_URL points at a reachable DB
(the docker compose stack provides one). Exercises the identity + persistence
path end-to-end: create tenant/role/user -> authenticate -> issue+decode token
-> persist a conversation turn -> read it back, asserting tenant scoping.

    RUN_INTEGRATION=1 python -m pytest tests/integration -q
"""
import os
import uuid

import pytest

RUN = os.environ.get("RUN_INTEGRATION") == "1"
pytestmark = pytest.mark.skipif(not RUN, reason="set RUN_INTEGRATION=1 to run")


async def _reset_schema():
    from app.platform.db.all_models import metadata
    from app.platform.db.postgres import get_engine

    async with get_engine().begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)


async def test_identity_and_persistence_roundtrip():
    from sqlalchemy import select

    from app.modules.conversation import repository as conv_repo
    from app.modules.conversation.models import Message
    from app.modules.identity import service as identity_service
    from app.modules.identity.models import Role
    from app.platform.auth import jwt as jwt_auth
    from app.platform.auth.dependencies import _ctx_from_jwt
    from app.platform.db.postgres import get_sessionmaker

    await _reset_schema()
    sessionmaker = get_sessionmaker()

    async with sessionmaker() as session:
        session.add(Role(name="member", permissions=["chat:write", "kb:read"]))
        tenant = await identity_service.create_tenant(
            session, name="Acme", slug="acme", plan="pro"
        )
        user = await identity_service.create_user(
            session,
            tenant_id=tenant.id,
            email="u@acme.test",
            password="pw12345",
            name="U",
            phone="555-0001",
            role_names=["member"],
        )
        await session.commit()
        tenant_id = tenant.id

    # authenticate -> tokens -> context
    async with sessionmaker() as session:
        authed, scopes = await identity_service.authenticate(session, "u@acme.test", "pw12345")
        tokens = await identity_service.issue_tokens(session, authed, scopes)
    claims = jwt_auth.decode_token(tokens["access_token"])
    assert claims["tid"] == str(tenant_id)
    ctx = await _ctx_from_jwt(tokens["access_token"])
    assert ctx.has("chat:write") and not ctx.has("admin:tenants")

    # persist a conversation turn and read it back, scoped to the tenant
    async with sessionmaker() as session:
        convo = await conv_repo.get_or_create_session(session, tenant_id, "user-1")
        await conv_repo.add_message(
            session, tenant_id=tenant_id, session_id=convo.id, role="user", content="hi"
        )
        await conv_repo.add_message(
            session, tenant_id=tenant_id, session_id=convo.id, role="assistant",
            content="hello", sources=["doc.pdf"], model="qwen2.5",
        )
        await session.commit()

    async with sessionmaker() as session:
        rows = (
            await session.execute(select(Message).where(Message.tenant_id == tenant_id))
        ).scalars().all()
        assert {r.role for r in rows} == {"user", "assistant"}
        # a different tenant sees nothing
        other = (
            await session.execute(select(Message).where(Message.tenant_id == uuid.uuid4()))
        ).scalars().all()
        assert other == []


async def test_register_and_provision_flow():
    """Self-serve register + bulk provision; end-user uses the tenant API key only."""
    from app.modules.admin import service as admin_service
    from app.modules.admin.schemas import ProvisionRow
    from app.modules.identity import service as identity_service
    from app.modules.identity.models import Role
    from app.platform.auth.dependencies import _ctx_from_api_key
    from app.platform.db.postgres import get_sessionmaker

    await _reset_schema()
    sm = get_sessionmaker()
    async with sm() as session:
        session.add(Role(name="admin", permissions=["*"]))
        await session.commit()

    # Public self-serve registration -> tenant + admin user + starter API key.
    async with sm() as session:
        result = await identity_service.register_workspace(
            session, workspace_name="Standalone Co", email="owner@standalone.test", password="pw123456"
        )
        await session.commit()
    assert result["api_key"].startswith("sk_")
    assert result["tenant_slug"] == "standalone-co"

    # The tenant API key authenticates an END-USER call with NO platform user.
    ctx = await _ctx_from_api_key(result["api_key"])
    assert ctx is not None and ctx.user_id is None and ctx.has("chat:write")

    # Duplicate email is rejected.
    async with sm() as session:
        with pytest.raises(identity_service.AuthError):
            await identity_service.register_workspace(
                session, workspace_name="Dup", email="owner@standalone.test", password="pw123456"
            )

    # Bulk provisioning is idempotent: 2 created, re-run skips both.
    rows = [
        ProvisionRow(name="Acme", admin_email="a@acme.test"),
        ProvisionRow(
            name="Globex", admin_email="g@globex.test",
            ds_type="mongo", ds_conn="mongodb://h", ds_db="d", ds_collections="chats",
        ),
    ]
    async with sm() as session:
        resp1 = await admin_service.provision_bulk(session, rows)
    assert resp1.created == 2 and resp1.errors == 0
    async with sm() as session:
        resp2 = await admin_service.provision_bulk(session, rows)
    assert resp2.skipped == 2 and resp2.created == 0
