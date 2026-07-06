"""MongoConversationConnector tests with a fake Motor db (no Mongo required).

Verifies document->ChatTurn mapping, active+archived merge, newest-`limit`
selection, and chronological ordering.
"""
from app.platform.connectors.base import ConnectorConfig
from app.platform.connectors.mongo_connector import MongoConversationConnector


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *_a, **_k):
        # docs are pre-sorted newest-first by the fake collection
        return self

    def limit(self, n):
        self._docs = self._docs[:n]
        return self

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d

        return gen()


class _FakeCollection:
    def __init__(self, docs):
        self._docs = sorted(docs, key=lambda d: d["timestamp"], reverse=True)

    def find(self, _query):
        return _FakeCursor(list(self._docs))


class _FakeDB:
    def __init__(self, collections):
        self._collections = collections

    def __getitem__(self, name):
        return self._collections[name]


def _doc(content, direction, ts):
    return {"content": content, "direction": direction, "timestamp": ts}


async def test_get_conversation_merges_and_orders(monkeypatch):
    active = _FakeCollection([
        _doc("newest user msg", "incoming", 100),
        _doc("", "incoming", 99),  # empty -> skipped
    ])
    archived = _FakeCollection([
        _doc("older bot reply", "outgoing", 50),
        _doc("oldest user msg", "incoming", 10),
    ])
    fake_db = _FakeDB({"whatsappchats": active, "whatsappchathistories": archived})

    connector = MongoConversationConnector(
        ConnectorConfig(type="mongo", conn="", db="rag", options={
            "collections": ["whatsappchats", "whatsappchathistories"],
        }),
        db=fake_db,
    )
    turns = await connector.get_conversation("919999", company_id="comp1", limit=10)

    # chronological order, empty message dropped, roles mapped from direction
    contents = [(t.role, t.content) for t in turns]
    assert contents == [
        ("user", "oldest user msg"),
        ("assistant", "older bot reply"),
        ("user", "newest user msg"),
    ]


async def test_get_conversation_adapts_to_custom_schema(monkeypatch):
    """A client whose docs use different field names works via field_mapping."""
    docs = [
        {"message_text": "hello", "sender_type": "customer", "ts": 5},
        {"message_text": "hi there", "sender_type": "agent", "ts": 9},
    ]
    fake_db = _FakeDB({"chat_log": _FakeCollection(
        [{**d, "timestamp": d["ts"]} for d in docs]  # _FakeCollection sorts on "timestamp"
    )})

    connector = MongoConversationConnector(
        ConnectorConfig(
            type="mongo", conn="", db="clientdb",
            options={"collections": ["chat_log"]},
            field_mapping={
                "company_field": "",            # this client doesn't partition by company
                "user_fields": ["customer_id"],
                "content_field": "message_text",
                "role_field": "sender_type",
                "role_user_value": "customer",
                "timestamp_field": "ts",
            },
        ),
        db=fake_db,
    )
    turns = await connector.get_conversation("u1", company_id="ignored", limit=10)
    assert [(t.role, t.content) for t in turns] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]
