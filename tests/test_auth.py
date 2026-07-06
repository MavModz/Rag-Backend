"""Auth unit tests: password hashing, JWT round-trip, API keys, RBAC, permission gate."""
import pytest
from fastapi import HTTPException

from app.platform.auth import api_keys, jwt as jwt_auth, rbac
from app.platform.auth.dependencies import require_permission
from app.platform.auth.password import hash_password, verify_password
from app.platform.tenancy.context import TenantContext


def test_password_hash_roundtrip():
    h = hash_password("s3cret!")
    assert h != "s3cret!"
    assert verify_password("s3cret!", h)
    assert not verify_password("wrong", h)


def test_jwt_access_roundtrip():
    token = jwt_auth.create_access_token(
        sub="u1", tid="t1", plan="pro", roles=["admin"], scopes=["*"]
    )
    claims = jwt_auth.decode_token(token)
    assert claims["sub"] == "u1"
    assert claims["tid"] == "t1"
    assert claims["scopes"] == ["*"]
    assert claims["type"] == "access"


def test_jwt_invalid_raises():
    with pytest.raises(jwt_auth.InvalidToken):
        jwt_auth.decode_token("not-a-token")


def test_api_key_generate_and_verify():
    full, prefix, key_hash = api_keys.generate_api_key()
    assert full.startswith("sk_")
    assert api_keys.key_prefix(full) == prefix
    assert api_keys.verify_key(full, key_hash)
    assert not api_keys.verify_key(full + "x", key_hash)


def test_rbac_expand_scopes_union_and_wildcard():
    assert rbac.expand_scopes([["chat:write"], ["kb:read", "chat:write"]]) == [
        "chat:write",
        "kb:read",
    ]
    assert rbac.expand_scopes([["*"], ["kb:read"]]) == ["*"]


def test_tenant_context_has():
    assert TenantContext("t", scopes=["*"]).has("anything")
    assert TenantContext("t", scopes=["kb:read"]).has("kb:read")
    assert not TenantContext("t", scopes=["kb:read"]).has("kb:write")


async def test_require_permission_allows_and_denies():
    dep = require_permission(rbac.Permission.KB_WRITE)
    ok = TenantContext("t", scopes=["kb:write"])
    assert await dep(ok) is ok

    denied = TenantContext("t", scopes=["kb:read"])
    with pytest.raises(HTTPException) as exc:
        await dep(denied)
    assert exc.value.status_code == 403
