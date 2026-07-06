"""Tests for memory learning (retrieve, reflect, context formatting)."""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.knowledge.rag import context_builder
from app.modules.memory import prompts, service
from app.modules.memory.vector_store import MemoryHit
from app.platform.gateway.types import GenerationResult
from app.platform.tenancy.context import TenantContext


def test_build_reflect_prompt_includes_q_and_a():
    out = prompts.build_reflect_prompt("refund?", "30 days", ["policy.pdf"])
    assert "refund?" in out
    assert "30 days" in out
    assert "policy.pdf" in out


def test_build_memory_context_empty():
    assert "No relevant learnings" in context_builder.build_memory_context([])


def test_build_memory_context_formats_hits():
    hits = [
        MemoryHit(
            summary="Refunds are within 30 days.",
            memory_type="verified_qa",
            score=0.9,
            source_question="What is the refund policy?",
        )
    ]
    out = context_builder.build_memory_context(hits)
    assert "verified qa" in out.lower()
    assert "30 days" in out
    assert "refund policy" in out.lower()


@patch("app.modules.memory.service.vector_store.search")
@patch("app.modules.memory.service.embeddings.embed_query")
def test_retrieve_disabled_returns_empty(mock_embed, mock_search):
    with patch("app.modules.memory.service.settings") as mock_settings:
        mock_settings.memory_enabled = False
        assert service.retrieve("tenant-1", "hello") == []
    mock_embed.assert_not_called()
    mock_search.assert_not_called()


@patch("app.modules.memory.service.vector_store.search")
@patch("app.modules.memory.service.embeddings.embed_query", return_value=[0.1, 0.2])
def test_retrieve_returns_search_results(mock_embed, mock_search):
    mock_search.return_value = [
        MemoryHit(summary="insight", memory_type="insight", score=0.8)
    ]
    with patch("app.modules.memory.service.settings") as mock_settings:
        mock_settings.memory_enabled = True
        mock_settings.memory_top_k = 3
        hits = service.retrieve("tenant-1", "refund policy")
    assert len(hits) == 1
    mock_embed.assert_called_once_with("refund policy")


@pytest.mark.asyncio
@patch("app.modules.memory.service.get_sessionmaker")
@patch("app.modules.memory.service.vector_store.upsert", return_value="vec-1")
@patch("app.modules.memory.service.embeddings.embed_query", return_value=[0.1])
@patch("app.modules.memory.service.get_gateway")
async def test_reflect_turn_skips_none(mock_gw, mock_embed, mock_upsert, mock_sm):
    gw = MagicMock()
    gw.generate = AsyncMock(return_value=GenerationResult(text="NONE", provider="ollama", model="m"))
    mock_gw.return_value = gw
    ctx = TenantContext(tenant_id=str(uuid.uuid4()), user_id="u1", scopes=["*"])
    await service.reflect_turn(ctx, uuid.uuid4(), "user1", "q", "a" * 50, [])
    mock_upsert.assert_not_called()
    mock_sm.assert_not_called()


@pytest.mark.asyncio
@patch("app.modules.memory.service.repository.create_memory", new_callable=AsyncMock)
@patch("app.modules.memory.service.get_sessionmaker")
@patch("app.modules.memory.service.vector_store.upsert", return_value="vec-1")
@patch("app.modules.memory.service.embeddings.embed_query", return_value=[0.1])
@patch("app.modules.memory.service.get_gateway")
async def test_reflect_turn_stores_insight(
    mock_gw, mock_embed, mock_upsert, mock_sm, mock_create
):
    gw = MagicMock()
    gw.generate = AsyncMock(
        return_value=GenerationResult(
            text="Customers should be told about the 30-day window.",
            provider="ollama",
            model="m",
        )
    )
    mock_gw.return_value = gw
    session = AsyncMock()
    session.commit = AsyncMock()
    mock_sm.return_value.return_value.__aenter__ = AsyncMock(return_value=session)
    mock_sm.return_value.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx = TenantContext(tenant_id=str(uuid.uuid4()), user_id="u1", scopes=["*"])
    await service.reflect_turn(ctx, uuid.uuid4(), "user1", "refund?", "answer " * 10, ["a.pdf"])
    mock_upsert.assert_called_once()
    mock_create.assert_called_once()
    session.commit.assert_called_once()
