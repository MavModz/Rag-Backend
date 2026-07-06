"""Tests for the data-source layer: SQL connector, secrets, and route wiring.

No live databases — exercises SQL building/mapping, identifier injection guard,
DSN normalization, secret encryption/redaction, and the API surface gate.
"""
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.config import settings
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.connectors import secrets as sec
from app.platform.connectors.base import ConnectorConfig
from app.platform.connectors.sql_connector import SqlConversationConnector, normalize_dsn
from app.platform.tenancy.context import TenantContext


# --- SQL connector ---
def _sql(**fm) -> SqlConversationConnector:
    return SqlConversationConnector(
        ConnectorConfig(type="sql", conn="postgresql+asyncpg://x", options={"table": "messages"}, field_mapping=fm)
    )


def test_normalize_dsn_upgrades_to_async_drivers():
    assert normalize_dsn("postgresql://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_dsn("postgres://u:p@h/db") == "postgresql+asyncpg://u:p@h/db"
    assert normalize_dsn("mysql://u:p@h/db") == "mysql+aiomysql://u:p@h/db"
    assert normalize_dsn("postgresql+asyncpg://x") == "postgresql+asyncpg://x"  # untouched


def test_sql_build_query_uses_mapping_and_binds_values():
    c = _sql(
        user_columns=["user_id"], company_column="org_id", content_column="body",
        role_column="sender", role_user_value="user", timestamp_column="created_at",
    )
    sql = c._build_sql(company_applies=True)
    assert "FROM messages" in sql
    assert "body AS content" in sql
    assert "sender AS role" in sql
    assert "user_id = :user" in sql
    assert "org_id = :company" in sql
    assert "ORDER BY created_at DESC LIMIT :limit" in sql


def test_sql_identifier_injection_is_blocked():
    bad = SqlConversationConnector(
        ConnectorConfig(type="sql", conn="x", options={"table": "messages; DROP TABLE users"}, field_mapping={})
    )
    with pytest.raises(ValueError):
        bad._build_sql(company_applies=False)


def test_sql_role_mapping():
    c = _sql(role_column="sender", role_user_value="user")
    assert c._to_turn({"content": "hi", "role": "user", "ts": 1}).role == "user"
    assert c._to_turn({"content": "yo", "role": "bot", "ts": 2}).role == "assistant"
    assert c._to_turn({"content": "   ", "role": "user", "ts": 3}) is None  # empty skipped


# --- secrets ---
def test_secret_encrypt_decrypt_redact(monkeypatch):
    monkeypatch.setattr(settings, "data_source_encryption_key", Fernet.generate_key().decode())
    uri = "mongodb://root:supersecret@host:27017/db"
    token = sec.encrypt_secret(uri)
    assert token.startswith("enc:")
    assert sec.decrypt_secret(token) == uri
    assert "supersecret" not in sec.redact_uri(uri)
    assert "****" in sec.redact_uri(uri)
    # non-encrypted values pass through decrypt unchanged
    assert sec.decrypt_secret("plain-text") == "plain-text"


# --- API surface ---
def test_data_source_routes_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in (
        "/data-sources",
        "/data-sources/test",
        "/data-sources/discover",
        "/data-sources/{source_id}",
    ):
        assert p in paths, f"missing data-source route: {p}"


async def test_data_source_permission_gate():
    dep = require_permission(Permission.DATASOURCES_MANAGE)
    with pytest.raises(HTTPException) as exc:
        await dep(TenantContext("t", scopes=["chat:write"]))
    assert exc.value.status_code == 403
    ok = TenantContext("t", scopes=[Permission.DATASOURCES_MANAGE])
    assert await dep(ok) is ok
