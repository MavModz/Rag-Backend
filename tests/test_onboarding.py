"""Onboarding tests: slugify, CSV parsing, data-source config build, the
provisioning-key gate, and the public-registration / provisioning toggles.

No live DB — DB-backed flows are covered by tests/integration/test_e2e.py.
"""
import types

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.config import settings
from app.modules.admin import service as admin_service
from app.modules.admin.schemas import ProvisionRow
from app.modules.identity.service import slugify
from app.platform.auth.dependencies import verify_provisioning_key
from app.platform.db.postgres import get_session


def test_slugify():
    assert slugify("My Company!") == "my-company"
    assert slugify("  Hello  World ") == "hello-world"
    assert slugify("") == "workspace"


def test_parse_csv():
    csv_bytes = (
        b"name,admin_email,plan,ds_type,ds_conn,ds_db,ds_collections\n"
        b"Acme,admin@acme.com,pro,mongo,mongodb://host,acmedb,chats\n"
    )
    rows = admin_service.parse_csv(csv_bytes)
    assert len(rows) == 1
    r = rows[0]
    assert r.name == "Acme"
    assert r.admin_email == "admin@acme.com"
    assert r.plan == "pro"
    assert r.ds_type == "mongo" and r.ds_db == "acmedb" and r.ds_collections == "chats"


def test_build_ds_config():
    mongo = ProvisionRow(
        name="x", admin_email="a@b.com", ds_type="mongo",
        ds_conn="mongodb://host", ds_db="d", ds_collections="a, b",
    )
    assert admin_service._build_ds_config(mongo) == {
        "uri": "mongodb://host", "db": "d", "collections": ["a", "b"],
    }
    sql = ProvisionRow(
        name="x", admin_email="a@b.com", ds_type="sql",
        ds_conn="postgresql://host", ds_table="messages",
    )
    assert admin_service._build_ds_config(sql) == {"dsn": "postgresql://host", "table": "messages"}


async def test_verify_provisioning_key(monkeypatch):
    # disabled (no key configured) -> 404
    monkeypatch.setattr(settings, "provisioning_api_key", "")
    with pytest.raises(HTTPException) as exc:
        await verify_provisioning_key(types.SimpleNamespace(headers={}))
    assert exc.value.status_code == 404

    # configured but wrong -> 401
    monkeypatch.setattr(settings, "provisioning_api_key", "secret")
    with pytest.raises(HTTPException) as exc:
        await verify_provisioning_key(types.SimpleNamespace(headers={"X-Provisioning-Key": "nope"}))
    assert exc.value.status_code == 401

    # correct -> passes
    assert await verify_provisioning_key(
        types.SimpleNamespace(headers={"X-Provisioning-Key": "secret"})
    ) is None


def test_onboarding_routes_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in ("/auth/register", "/admin/provision", "/admin/provision/csv", "/provisioning/tenants"):
        assert p in paths


def test_register_disabled_returns_403(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "allow_public_registration", False)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as client:
            r = client.post(
                "/auth/register",
                json={"workspace_name": "W", "email": "a@b.com", "password": "password1"},
            )
            assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_provisioning_disabled_returns_404(monkeypatch):
    from app.main import app

    monkeypatch.setattr(settings, "provisioning_api_key", "")

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as client:
            r = client.post("/provisioning/tenants", json={"name": "X", "admin_email": "a@b.com"})
            assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_session, None)
