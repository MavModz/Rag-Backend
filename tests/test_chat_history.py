"""Pushed conversation history on /chat (WhatsApp Option B)."""
from __future__ import annotations

import asyncio

from app.modules.conversation import service as chat_service
from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.connectors.base import ChatTurn
from app.platform.security.sanitize import InvalidInput, sanitize_history_turns


def test_handle_uses_pushed_history_and_skips_connector(monkeypatch):
    captured: dict = {}

    def fake_retrieve(
        company_id, query, top_k=None, *, kb_scope="support", product=None, retrieval_profile=None
    ):
        captured["retrieve"] = True
        return [
            RetrievedChunk(text="Fees are Rs.49.", source="fees.pdf", score=0.9, chunk_index=0),
        ]

    async def fail_get_conversation(*_args, **_kwargs):
        raise AssertionError("connector should not be called when history is pushed")

    async def fake_generate_answer(
        kb_context,
        history,
        question,
        tenant_ctx=None,
        memory_context="",
        *,
        prompt_source="default",
        chatbot_channel=None,
        procedural=False,
        sources=None,
    ):
        captured["history"] = history
        return "The course fee is Rs.49."

    class FakeConnector:
        async def get_conversation(self, external_user_id, company_id, limit=None):
            return await fail_get_conversation(external_user_id, company_id, limit)

    class FakeRegistry:
        async def get_conversation_connector(self, tenant_ctx=None, company_id=None):
            return FakeConnector()

    monkeypatch.setattr(chat_service.retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_service.memory_service, "retrieve", lambda *_a, **_k: [])
    monkeypatch.setattr(
        chat_service.connector_registry, "get_connector_registry", lambda: FakeRegistry()
    )
    monkeypatch.setattr(chat_service.agent, "generate_answer", fake_generate_answer)

    pushed = [
        ChatTurn(role="user", content="Course fees"),
        ChatTurn(role="assistant", content="Our masterclass is Rs.49."),
    ]

    result = asyncio.run(
        chat_service.handle(
            company_id="6a46466d808b90405db6e751",
            user_number="917727902031",
            message="Do you have a trial?",
            history_turns=pushed,
        )
    )

    assert result.answer == "The course fee is Rs.49."
    assert "Course fees" in captured["history"]
    assert "Rs.49." in captured["history"]


def test_handle_empty_pushed_history_skips_connector(monkeypatch):
    called = {"connector": False}

    async def fake_get_conversation(*_args, **_kwargs):
        called["connector"] = True
        return []

    async def fake_generate_answer(*_args, **_kwargs):
        return "Hello"

    class FakeConnector:
        async def get_conversation(self, external_user_id, company_id, limit=None):
            return await fake_get_conversation(external_user_id, company_id, limit)

    class FakeRegistry:
        async def get_conversation_connector(self, tenant_ctx=None, company_id=None):
            return FakeConnector()

    monkeypatch.setattr(chat_service.retriever, "retrieve", lambda *_a, **_k: [])
    monkeypatch.setattr(chat_service.memory_service, "retrieve", lambda *_a, **_k: [])
    monkeypatch.setattr(
        chat_service.connector_registry, "get_connector_registry", lambda: FakeRegistry()
    )
    monkeypatch.setattr(chat_service.agent, "generate_answer", fake_generate_answer)

    asyncio.run(
        chat_service.handle(
            company_id="comp1",
            user_number="91999",
            message="Hi",
            history_turns=[],
        )
    )

    assert called["connector"] is False


def test_sanitize_history_turns_keeps_most_recent_when_over_limit():
    class Turn:
        def __init__(self, role: str, content: str):
            self.role = role
            self.content = content

    turns = [Turn("user", f"message {i}") for i in range(12)]
    cleaned = sanitize_history_turns(turns, max_turns=10)
    assert len(cleaned) == 10
    assert cleaned[0] == ("user", "message 2")
    assert cleaned[-1] == ("user", "message 11")


def test_sanitize_history_role_rejects_invalid():
    class Turn:
        role = "system"
        content = "hello"

    try:
        sanitize_history_turns([Turn()], max_turns=10)
    except InvalidInput as exc:
        assert "role" in str(exc)
    else:
        raise AssertionError("expected InvalidInput")
