"""Data-source service: encrypt-on-write, redact-on-read, test, and discover.

Business logic only. Connection secrets are encrypted before persisting and
redacted before returning. ``test``/``discover`` operate on the connection string
submitted in the request (plaintext from the UI form).
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.datasources import constants as ds_constants
from app.modules.datasources import repository as repo
from app.modules.datasources import schemas
from app.platform.connectors.models import DataSource
from app.platform.connectors.registry import build_connector, config_from_row_fields
from app.platform.connectors.secrets import encrypt_secret, redact_uri, secret_key_for


def _encrypt_config(source_type: str, config: dict) -> dict:
    cfg = dict(config or {})
    secret_key = secret_key_for(source_type)
    if cfg.get(secret_key):
        cfg[secret_key] = encrypt_secret(cfg[secret_key])
    return cfg


def to_out(src: DataSource) -> schemas.DataSourceOut:
    cfg = dict(src.config or {})
    secret_key = secret_key_for(src.type)
    if cfg.get(secret_key):
        cfg[secret_key] = redact_uri(cfg[secret_key])
    return schemas.DataSourceOut(
        id=str(src.id),
        type=src.type,
        name=src.name,
        config=cfg,
        field_mapping=src.field_mapping or {},
        enabled=src.enabled,
        created_at=src.created_at,
    )


def whatsapp_preset() -> schemas.WhatsAppDataSourcePreset:
    return schemas.WhatsAppDataSourcePreset(
        config=dict(ds_constants.WHATSAPP_MONGO_CONFIG_TEMPLATE),
        field_mapping=dict(ds_constants.WHATSAPP_MONGO_FIELD_MAPPING),
    )


def _invalidate_connector_cache(source_id: uuid.UUID) -> None:
    from app.platform.connectors.registry import get_connector_registry

    get_connector_registry().invalidate_source(str(source_id))


async def create(
    session: AsyncSession, tenant_id: uuid.UUID, payload: schemas.DataSourceCreate
) -> DataSource:
    src = DataSource(
        tenant_id=tenant_id,
        type=payload.type,
        name=payload.name,
        config=_encrypt_config(payload.type, payload.config),
        field_mapping=payload.field_mapping,
        enabled=payload.enabled,
    )
    row = await repo.add(session, src)
    _invalidate_connector_cache(row.id)
    return row


async def update(
    session: AsyncSession, src: DataSource, payload: schemas.DataSourceUpdate
) -> DataSource:
    if payload.name is not None:
        src.name = payload.name
    if payload.field_mapping is not None:
        src.field_mapping = payload.field_mapping
    if payload.enabled is not None:
        src.enabled = payload.enabled
    if payload.config is not None:
        src.config = _encrypt_config(src.type, payload.config)
    await session.flush()
    _invalidate_connector_cache(src.id)
    return src


async def _close(connector) -> None:
    if hasattr(connector, "aclose"):
        await connector.aclose()
    elif hasattr(connector, "close"):
        connector.close()


async def delete_source(session: AsyncSession, src: DataSource) -> None:
    source_id = src.id
    await repo.delete(session, src)
    _invalidate_connector_cache(source_id)


async def test_connection(payload: schemas.TestRequest) -> schemas.TestResult:
    try:
        config = config_from_row_fields(
            type=payload.type, config=payload.config, field_mapping=payload.field_mapping
        )
        connector = build_connector(config)
        try:
            await connector.test_connection()
        finally:
            await _close(connector)
        return schemas.TestResult(ok=True)
    except Exception as exc:  # noqa: BLE001 - report the failure to the caller
        return schemas.TestResult(ok=False, error=str(exc))


async def discover(payload: schemas.DiscoverRequest) -> schemas.DiscoverResult:
    result = schemas.DiscoverResult()
    cfg = payload.config or {}
    conn = cfg.get(secret_key_for(payload.type), "")

    if payload.type == "mongo":
        from motor.motor_asyncio import AsyncIOMotorClient

        client = AsyncIOMotorClient(conn)
        try:
            db = cfg.get("db")
            if not db:
                names = await client.list_database_names()
                result.databases = [n for n in names if n not in ("admin", "local", "config")]
            elif not payload.target:
                result.collections = await client[db].list_collection_names()
            else:
                doc = await client[db][payload.target].find_one()
                result.fields = sorted(doc.keys()) if doc else []
        finally:
            client.close()
    else:  # sql family
        from sqlalchemy import inspect
        from sqlalchemy.ext.asyncio import create_async_engine

        from app.platform.connectors.sql_connector import normalize_dsn

        engine = create_async_engine(normalize_dsn(conn))
        try:
            async with engine.connect() as c:
                if not payload.target:
                    result.tables = await c.run_sync(lambda cc: inspect(cc).get_table_names())
                else:
                    cols = await c.run_sync(lambda cc: inspect(cc).get_columns(payload.target))
                    result.fields = [col["name"] for col in cols]
        finally:
            await engine.dispose()
    return result
