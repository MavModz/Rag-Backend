"""Connector abstractions and shared data contracts.

``ChatTurn`` is the normalized conversation turn every conversation connector
emits, regardless of the underlying store. ``ConversationConnector`` is the
capability interface the Conversation Service depends on; concrete connectors
(Mongo today, MySQL/others later) implement it. ``ConnectorConfig`` carries the
per-source connection + field-mapping details, resolved per tenant from the
``data_sources`` table (Phase 6+).

Note on identifiers: ``company_id`` here is the tenant's id *in the external
business system* (e.g. the WhatsApp/Mongo company ObjectId). The platform's
internal ``tenant_id`` maps to it via the data-source field mapping.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ChatTurn:
    """A single message in a conversation, normalized for prompt building."""

    role: str  # "user" (incoming) or "assistant" (outgoing)
    content: str
    timestamp: object | None = None


@dataclass
class ConnectorConfig:
    """Connection + mapping details for one external data source.

    ``conn`` is the (decrypted) connection string. ``options`` holds non-secret
    connection details (db name, collections, table). ``field_mapping`` adapts the
    connector to the client's own schema — its keys are documented per connector
    (see ``mongo_connector`` / ``sql_connector``). This makes the platform
    independent of any single database or schema.
    """

    type: str = "mongo"
    conn: str = ""                                     # connection string (uri/dsn)
    db: str = ""
    options: dict = field(default_factory=dict)        # collections / table / etc.
    field_mapping: dict = field(default_factory=dict)  # client schema -> our fields

    # Back-compat alias: older code referenced ``.uri``.
    @property
    def uri(self) -> str:
        return self.conn


class ConversationConnector(ABC):
    """Read a user's prior conversation from an external business system."""

    @abstractmethod
    async def get_conversation(
        self,
        external_user_id: str,
        company_id: str,
        limit: int | None = None,
    ) -> list[ChatTurn]:
        """Most recent turns ordered oldest -> newest (prompt-ready)."""
