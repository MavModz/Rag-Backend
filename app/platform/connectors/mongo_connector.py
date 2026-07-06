"""MongoDB conversation connector (read-only), schema-agnostic.

Reads a user's prior conversation from a tenant's OWN MongoDB. The platform has no
global Mongo — every connector opens its own client from the data source's
connection string. All field names and collections come from config /
field_mapping, so any client's schema works.

config.conn:    the tenant's Mongo URI
config.db:      database name
config.options:
    collections: [str, ...]   # one or more collections, queried + merged
field_mapping (all optional; defaults shown):
    company_field        "company_id"   # field holding the tenant's external id (or "" to skip)
    company_is_object_id true           # convert the company value to a Mongo ObjectId
    company_id_value      None          # fixed external id (else the request's company_id is used)
    user_fields           ["from","to"] # fields matched against the user's id
    content_field         "content"
    role_field            "direction"
    role_user_value       "incoming"    # value of role_field that means the end-user spoke
    timestamp_field       "timestamp"

We never write to the tenant's collections.
"""
from __future__ import annotations

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings
from app.platform.connectors.base import ChatTurn, ConnectorConfig, ConversationConnector
from app.platform.observability.logging import get_logger

logger = get_logger(__name__)


def _to_object_id(value: str) -> ObjectId | str:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return value


class MongoConversationConnector(ConversationConnector):
    def __init__(self, config: ConnectorConfig | None = None, db: AsyncIOMotorDatabase | None = None) -> None:
        self.config = config or ConnectorConfig(type="mongo")
        self._db_override = db  # injectable for tests
        self._own_client: AsyncIOMotorClient | None = None
        fm = self.config.field_mapping
        self._company_field = fm.get("company_field", "company_id")
        self._company_is_oid = fm.get("company_is_object_id", True)
        self._company_value = fm.get("company_id_value")
        self._user_fields = fm.get("user_fields", ["from", "to"])
        self._content_field = fm.get("content_field", "content")
        self._role_field = fm.get("role_field", "direction")
        self._role_user_value = fm.get("role_user_value", "incoming")
        self._ts_field = fm.get("timestamp_field", "timestamp")
        self._collections = self.config.options.get("collections") or []

    def _db(self) -> AsyncIOMotorDatabase:
        if self._db_override is not None:
            return self._db_override
        if self._own_client is None:
            if not self.config.conn:
                raise RuntimeError("Mongo connector has no connection string configured.")
            self._own_client = AsyncIOMotorClient(self.config.conn)
            logger.info("Opened Mongo client for connector db=%s", self.config.db)
        return self._own_client[self.config.db]

    def _doc_to_turn(self, doc: dict) -> ChatTurn | None:
        content = doc.get(self._content_field) or ""
        content = content.strip() if isinstance(content, str) else str(content)
        if not content:
            return None
        role = "user" if doc.get(self._role_field) == self._role_user_value else "assistant"
        return ChatTurn(role=role, content=content, timestamp=doc.get(self._ts_field))

    def _build_query(self, external_user_id: str, company_id: str) -> dict:
        query: dict = {}
        company_id = self._company_value or company_id
        if self._company_field and company_id:
            query[self._company_field] = (
                _to_object_id(company_id) if self._company_is_oid else company_id
            )
        if self._user_fields:
            query["$or"] = [{f: external_user_id} for f in self._user_fields]
        return query

    async def _fetch_recent(self, collection: str, query: dict, limit: int) -> list[ChatTurn]:
        cursor = self._db()[collection].find(query).sort(self._ts_field, -1).limit(limit)
        turns: list[ChatTurn] = []
        async for doc in cursor:
            turn = self._doc_to_turn(doc)
            if turn is not None:
                turns.append(turn)
        return turns

    async def get_conversation(
        self,
        external_user_id: str,
        company_id: str,
        limit: int | None = None,
    ) -> list[ChatTurn]:
        limit = limit or settings.history_limit
        if not self._collections:
            return []
        query = self._build_query(external_user_id, company_id)

        merged: list[ChatTurn] = []
        for collection in self._collections:
            merged.extend(await self._fetch_recent(collection, query, limit))

        merged.sort(key=lambda t: (t.timestamp is not None, t.timestamp), reverse=True)
        merged = merged[:limit]
        merged.reverse()  # chronological

        logger.info(
            "Loaded %d turns from %d collection(s) for user=%s company=%s",
            len(merged), len(self._collections), external_user_id, company_id,
        )
        return merged

    async def test_connection(self) -> None:
        """Raise if the connection is unreachable (used by /data-sources/test)."""
        client = AsyncIOMotorClient(self.config.conn)
        try:
            await client.admin.command("ping")
        finally:
            client.close()

    def close(self) -> None:
        if self._own_client is not None:
            self._own_client.close()
            self._own_client = None
