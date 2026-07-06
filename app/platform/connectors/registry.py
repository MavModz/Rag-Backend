"""Connector registry: resolve the right connector for a tenant.

Per-tenant resolution: reads the tenant's primary enabled conversation
``data_sources`` row, decrypts its connection string, builds a connector from its
config + field_mapping, and caches it per source (rebuilt when the row changes).
Tenants without a configured source (and the anonymous/dev context) fall back to
the settings-based default Mongo, preserving the original behavior with zero
migration.

This is what makes the platform database-independent: each tenant points the
agents at their own DB/collections via the data-source they registered.
"""
from __future__ import annotations

import uuid

from app.platform.connectors.base import ChatTurn, ConnectorConfig, ConversationConnector
from app.platform.connectors.mongo_connector import MongoConversationConnector
from app.platform.connectors.secrets import decrypt_secret, secret_key_for
from app.platform.connectors.sql_connector import SqlConversationConnector
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


class NullConversationConnector(ConversationConnector):
    """Used when a tenant has no configured data source — yields no history.

    The platform is DB-independent: with no source registered, chat still works
    (grounded on the knowledge base) and simply has no prior conversation.
    """

    async def get_conversation(self, external_user_id, company_id, limit=None) -> list[ChatTurn]:
        return []

# Connector classes by data-source type. SQL types share one connector.
_CONNECTOR_CLASSES = {
    "mongo": MongoConversationConnector,
    "sql": SqlConversationConnector,
    "mysql": SqlConversationConnector,
    "postgres": SqlConversationConnector,
    "postgresql": SqlConversationConnector,
}
CONVERSATION_TYPES = tuple(_CONNECTOR_CLASSES.keys())


def config_from_row_fields(
    *, type: str, config: dict, field_mapping: dict
) -> ConnectorConfig:
    """Build a ConnectorConfig from stored (encrypted) row fields, decrypting the secret."""
    cfg = dict(config or {})
    secret_key = secret_key_for(type)
    conn = decrypt_secret(cfg.get(secret_key, ""))
    options = {k: v for k, v in cfg.items() if k not in (secret_key, "db")}
    return ConnectorConfig(
        type=type,
        conn=conn,
        db=cfg.get("db", ""),
        options=options,
        field_mapping=field_mapping or {},
    )


def build_connector(config: ConnectorConfig) -> ConversationConnector:
    """Instantiate a connector for an (already-decrypted) config. Used by test/discover too."""
    cls = _CONNECTOR_CLASSES.get(config.type)
    if cls is None:
        raise ValueError(f"Unsupported data-source type: {config.type!r}")
    return cls(config)


async def _close_connector(connector: ConversationConnector) -> None:
    if hasattr(connector, "aclose"):
        try:
            await connector.aclose()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass
    elif hasattr(connector, "close"):
        try:
            connector.close()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


class ConnectorRegistry:
    def __init__(self) -> None:
        self._default: ConversationConnector | None = None
        # source_id -> (row_version, connector)
        self._cache: dict[str, tuple[str, ConversationConnector]] = {}

    def _default_connector(self) -> ConversationConnector:
        # No global DB: tenants without a configured source get an empty history.
        if self._default is None:
            self._default = NullConversationConnector()
        return self._default

    async def _load_primary_source(self, tenant_id: uuid.UUID):
        from sqlalchemy import select

        from app.platform.connectors.models import DataSource
        from app.platform.db.postgres import get_sessionmaker

        try:
            sessionmaker = get_sessionmaker()
            async with sessionmaker() as session:
                res = await session.execute(
                    select(DataSource)
                    .where(
                        DataSource.tenant_id == tenant_id,
                        DataSource.enabled.is_(True),
                        DataSource.type.in_(CONVERSATION_TYPES),
                    )
                    .order_by(DataSource.created_at.asc())
                )
                return res.scalars().first()
        except Exception as exc:  # noqa: BLE001 - DB down -> fall back to default
            logger.warning("Could not load data source for tenant %s: %s", tenant_id, exc)
            return None

    async def get_conversation_connector(
        self, tenant_ctx, company_id: str | None = None
    ) -> ConversationConnector:
        tenant_id = tenant_ctx.tenant_uuid() if tenant_ctx else None
        if tenant_id is None:
            return self._default_connector()

        row = await self._load_primary_source(tenant_id)
        if row is None:
            return self._default_connector()

        source_id = str(row.id)
        version = row.updated_at.isoformat() if row.updated_at else "0"
        cached = self._cache.get(source_id)
        if cached and cached[0] == version:
            return cached[1]
        if cached:
            await _close_connector(cached[1])

        config = config_from_row_fields(
            type=row.type, config=row.config, field_mapping=row.field_mapping
        )
        connector = build_connector(config)
        self._cache[source_id] = (version, connector)
        logger.info("Built %s connector for tenant=%s source=%s", row.type, tenant_id, source_id)
        return connector

    async def close_all(self) -> None:
        for _, connector in self._cache.values():
            await _close_connector(connector)
        self._cache.clear()
        if self._default is not None:
            await _close_connector(self._default)
            self._default = None

    def invalidate_source(self, source_id: str) -> None:
        """Drop a cached connector after admin/tenant updates a data source."""
        cached = self._cache.pop(source_id, None)
        if cached is None:
            return
        connector = cached[1]
        if hasattr(connector, "close"):
            try:
                connector.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass


_registry: ConnectorRegistry | None = None


def get_connector_registry() -> ConnectorRegistry:
    global _registry
    if _registry is None:
        _registry = ConnectorRegistry()
    return _registry
