"""Generic SQL conversation connector (Postgres / MySQL), schema-agnostic.

Reads a user's prior conversation from a tenant's own relational DB via async
SQLAlchemy. Table and column names come from field_mapping, so any client's
schema works. Column/table identifiers are validated against a strict pattern
(values are always bound parameters) to prevent SQL injection.

config.conn:      async DSN (postgresql+asyncpg://… or mysql+aiomysql://…);
                  common sync forms are auto-upgraded by ``normalize_dsn``.
config.options:   table: str            # table to read from (or…)
                  query: str            # advanced: raw SQL using :user/:company/:limit
field_mapping:
    user_columns      ["user_id"]   # columns matched against the user's id
    company_column    None          # optional tenant/company partition column
    company_id_value  None          # fixed external id (else request company_id)
    content_column    "content"
    role_column       None          # column holding sender role (recommended)
    role_user_value   "incoming"    # value of role_column meaning the end-user spoke
    timestamp_column  "created_at"
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings
from app.platform.connectors.base import ChatTurn, ConnectorConfig, ConversationConnector
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ident(name: str, what: str) -> str:
    if not name or not _IDENT.match(name):
        raise ValueError(f"Invalid {what} (must be a plain identifier): {name!r}")
    return name


def normalize_dsn(dsn: str) -> str:
    """Upgrade common sync DSNs to their async drivers."""
    scheme = dsn.split("://", 1)[0] if "://" in dsn else ""
    if scheme == "postgres" or scheme == "postgresql":
        return dsn.replace(f"{scheme}://", "postgresql+asyncpg://", 1)
    if scheme == "mysql":
        return dsn.replace("mysql://", "mysql+aiomysql://", 1)
    return dsn


class SqlConversationConnector(ConversationConnector):
    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self._engine: AsyncEngine | None = None
        fm = config.field_mapping
        self._user_columns = fm.get("user_columns") or ["user_id"]
        self._company_column = fm.get("company_column")
        self._company_value = fm.get("company_id_value")
        self._content_column = fm.get("content_column", "content")
        self._role_column = fm.get("role_column")
        self._role_user_value = fm.get("role_user_value", "incoming")
        self._timestamp_column = fm.get("timestamp_column", "created_at")
        self._table = config.options.get("table")
        self._raw_query = config.options.get("query")

    def _get_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                normalize_dsn(self.config.conn), pool_pre_ping=True, pool_size=2, max_overflow=2
            )
        return self._engine

    def _build_sql(self, company_applies: bool) -> str:
        content = _ident(self._content_column, "content_column")
        ts = _ident(self._timestamp_column, "timestamp_column")
        table = _ident(self._table or "", "table")
        select = [f"{content} AS content", f"{ts} AS ts"]
        if self._role_column:
            select.append(f"{_ident(self._role_column, 'role_column')} AS role")
        user_cols = [_ident(c, "user_column") for c in self._user_columns]
        where = "(" + " OR ".join(f"{c} = :user" for c in user_cols) + ")"
        if company_applies:
            where += f" AND {_ident(self._company_column, 'company_column')} = :company"
        return f"SELECT {', '.join(select)} FROM {table} WHERE {where} ORDER BY {ts} DESC LIMIT :limit"

    def _to_turn(self, row: dict) -> ChatTurn | None:
        content = row.get("content") or ""
        content = content.strip() if isinstance(content, str) else str(content)
        if not content:
            return None
        if self._role_column:
            role = "user" if row.get("role") == self._role_user_value else "assistant"
        else:
            role = "user"
        return ChatTurn(role=role, content=content, timestamp=row.get("ts"))

    async def get_conversation(
        self,
        external_user_id: str,
        company_id: str,
        limit: int | None = None,
    ) -> list[ChatTurn]:
        limit = limit or settings.history_limit
        cid = self._company_value or company_id
        company_applies = bool(self._company_column and cid)
        params = {"user": external_user_id, "limit": limit}
        if company_applies:
            params["company"] = cid

        sql = self._raw_query or self._build_sql(company_applies)
        async with self._get_engine().connect() as conn:
            result = await conn.execute(text(sql), params)
            rows = result.mappings().all()

        turns = [t for t in (self._to_turn(dict(r)) for r in rows) if t is not None]
        turns.reverse()  # fetched newest-first -> chronological
        logger.info("Loaded %d turns (SQL) for user=%s company=%s", len(turns), external_user_id, company_id)
        return turns

    async def test_connection(self) -> None:
        async with self._get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def aclose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
