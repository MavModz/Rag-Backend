"""Conversation service orchestration test with all external layers mocked.

Uses asyncio.run (no pytest-asyncio dependency) and monkeypatches the Knowledge,
connector, and agent layers so no Ollama/Qdrant/Mongo is required.
"""
import asyncio

from app.modules.conversation import service as chat_service
from app.modules.knowledge.rag.vector_store import RetrievedChunk
from app.platform.connectors.base import ChatTurn


def test_handle_wires_layers_and_returns_sources(monkeypatch):
    captured = {}

    def fake_retrieve(
        company_id, query, top_k=None, *, kb_scope="support", product=None, retrieval_profile=None
    ):
        captured["retrieve"] = (company_id, query, kb_scope, product, retrieval_profile)
        return [
            RetrievedChunk(text="Plan A costs $10.", source="pricing.pdf", score=0.9, chunk_index=0),
            RetrievedChunk(text="Plan B costs $20.", source="pricing.pdf", score=0.8, chunk_index=1),
        ]

    async def fake_get_conversation(external_user_id, company_id, limit=None):
        captured["history"] = (external_user_id, company_id)
        return [ChatTurn(role="user", content="Hi")]

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
        captured["prompt"] = (
            kb_context,
            history,
            question,
            memory_context,
            procedural,
            prompt_source,
            chatbot_channel,
        )
        return "Plan A is $10 and Plan B is $20."

    def fake_memory_retrieve(company_id, query):
        return []

    class FakeConnector:
        async def get_conversation(self, external_user_id, company_id, limit=None):
            return await fake_get_conversation(external_user_id, company_id, limit)

    class FakeRegistry:
        async def get_conversation_connector(self, tenant_ctx=None, company_id=None):
            return FakeConnector()

    monkeypatch.setattr(chat_service.retriever, "retrieve", fake_retrieve)
    monkeypatch.setattr(chat_service.memory_service, "retrieve", fake_memory_retrieve)
    monkeypatch.setattr(
        chat_service.connector_registry, "get_connector_registry", lambda: FakeRegistry()
    )
    monkeypatch.setattr(
        chat_service.agent, "generate_answer", fake_generate_answer
    )

    result = asyncio.run(
        chat_service.handle(
            company_id="comp1", user_number="91999", message="What are the prices?"
        )
    )

    assert result.answer == "Plan A is $10 and Plan B is $20."
    assert result.sources == ["pricing.pdf"]  # deduped
    # tenant scoping propagated to both retrieval and history
    assert captured["retrieve"] == ("comp1", "What are the prices?", "support", "lms", "platform_and_tenant")
    assert captured["history"] == ("91999", "comp1")
    # KB text made it into the generation prompt
    assert "Plan A costs $10." in captured["prompt"][0]
