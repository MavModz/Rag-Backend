"""Admin surface is registered and permission-gated.

DB-backed behavior is covered by the integration test; here we assert the routes
exist and that a context lacking admin scope is rejected by the gate.
"""
import pytest
from fastapi import HTTPException

from app.platform.auth import rbac
from app.platform.auth.dependencies import require_permission
from app.platform.tenancy.context import TenantContext


def test_admin_routes_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in (
        "/admin/tenants",
        "/admin/tenants/{tenant_id}",
        "/admin/tenants/{tenant_id}/users",
        "/admin/tenants/{tenant_id}/api-keys",
        "/admin/api-keys/{key_id}/revoke",
        "/admin/roles",
    ):
        assert p in paths, f"missing admin route: {p}"


async def test_admin_permission_gate_denies_non_admin():
    dep = require_permission(rbac.Permission.ADMIN_TENANTS)
    member = TenantContext("t", scopes=["chat:write", "kb:read"])
    with pytest.raises(HTTPException) as exc:
        await dep(member)
    assert exc.value.status_code == 403
    # superadmin wildcard passes
    superadmin = TenantContext("t", scopes=["*"])
    assert await dep(superadmin) is superadmin
