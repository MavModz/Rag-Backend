"""RequestContext auth resolution and tracing bind."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

from app.config import settings
from app.platform.auth import jwt as platform_jwt
from app.platform.auth.dependencies import get_request_context
from app.platform.tenancy.constants import AuthMode, PRODUCT_LMS
from app.platform.tenancy.request_context import RequestContext, agent_to_kb_scope


def _request(
    *,
    api_key: str | None = None,
    bearer: str | None = None,
    product: str | None = None,
    agent: str | None = None,
    session_id: str | None = None,
    acting_user_id: str | None = None,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if api_key:
        headers.append((b"x-api-key", api_key.encode()))
    if bearer:
        headers.append((b"authorization", f"Bearer {bearer}".encode()))
    if product:
        headers.append((b"x-product", product.encode()))
    if agent:
        headers.append((b"x-agent", agent.encode()))
    if session_id:
        headers.append((b"x-session-id", session_id.encode()))
    if acting_user_id:
        headers.append((b"x-acting-user-id", acting_user_id.encode()))
    scope = {"type": "http", "headers": headers, "method": "POST", "path": "/chat"}
    return Request(scope)


def test_request_context_anonymous_when_allowed(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_anonymous", True)
    ctx = asyncio.run(get_request_context(_request()))
    assert ctx.auth_mode == AuthMode.ANONYMOUS
    assert ctx.tenant_id == "anonymous"


def test_request_context_headers_set_agent_kb_scope(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_anonymous", True)
    ctx = asyncio.run(get_request_context(_request(agent="quiz", product="lms")))
    assert ctx.product == "lms"
    assert ctx.agent == "quiz"
    assert ctx.effective_kb_scope() == "quiz"


def test_agent_to_kb_scope_whatsapp_maps_support():
    assert agent_to_kb_scope("whatsapp") == "support"


def test_request_context_platform_jwt(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_anonymous", False)
    tid = str(uuid.uuid4())
    token = platform_jwt.create_access_token(
        sub=str(uuid.uuid4()),
        tid=tid,
        plan="pro",
        roles=["admin"],
        scopes=["chat:write"],
    )

    async def fake_platform_jwt(token_str: str):
        from app.platform.tenancy.context import TenantContext

        return TenantContext(tenant_id=tid, scopes=["chat:write"])

    monkeypatch.setattr(
        "app.platform.auth.dependencies._ctx_from_platform_jwt", fake_platform_jwt
    )
    ctx = asyncio.run(get_request_context(_request(bearer=token)))
    assert ctx.auth_mode == AuthMode.PLATFORM_JWT
    assert ctx.tenant_id == tid


def test_product_jwt_resolves_org_id(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_anonymous", False)
    monkeypatch.setattr(settings, "lms_jwt_secret", "lms-test-secret")
    org = "org-acme-001"
    tid = uuid.uuid4()

    token = jwt.encode(
        {
            "sub": "student-1",
            "org_id": org,
            "product": "lms",
            "roles": ["student"],
            "type": "access",
        },
        settings.lms_jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    class FakeTenant:
        id = tid
        plan = "free"
        budget_monthly = 0.0
        priority = 0
        status = "active"

    async def fake_lookup(session, org_id: str):
        assert org_id == org
        return FakeTenant()

    monkeypatch.setattr(
        "app.platform.auth.dependencies.repository.get_tenant_by_external_org_id",
        fake_lookup,
    )

    ctx = asyncio.run(get_request_context(_request(bearer=token, product="lms")))
    assert ctx.auth_mode == AuthMode.PRODUCT_USER_JWT
    assert ctx.tenant_id == str(tid)
    assert ctx.external_user_id == "student-1"
    assert ctx.product == "lms"


def test_invalid_credentials_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "auth_allow_anonymous", False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_request_context(_request(bearer="not-valid")))
    assert exc.value.status_code == 401


def test_request_context_conversation_key_prefers_session():
    ctx = RequestContext.anonymous()
    ctx.session_id = "sess-1"
    ctx.external_user_id = "phone-1"
    assert ctx.conversation_key() == "sess-1"
