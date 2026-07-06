"""Chatbot configuration unit tests (no live DB)."""
from __future__ import annotations

import uuid

import pytest

from app.modules.chatbot import constants as cb_const
from app.modules.chatbot import service as chatbot_service
from app.modules.chatbot.models import ChatbotConfig
from app.platform.tenancy.request_context import RequestContext


def test_resolve_channel_whatsapp_agent():
    ctx = RequestContext(
        tenant_id="t1",
        scopes=["chat:write"],
        agent=cb_const.CHANNEL_WHATSAPP,
    )
    assert chatbot_service.resolve_channel(ctx) == cb_const.CHANNEL_WHATSAPP


def test_resolve_channel_whatsapp_header_only():
    ctx = RequestContext(
        tenant_id="t1",
        scopes=["chat:write"],
        channel=cb_const.CHANNEL_WHATSAPP,
    )
    assert chatbot_service.resolve_channel(ctx) is None


def test_resolve_channel_web_returns_none():
    ctx = RequestContext(tenant_id="t1", scopes=["chat:write"], channel="web")
    assert chatbot_service.resolve_channel(ctx) is None


def test_build_system_prompt_includes_tone_and_goals():
    row = ChatbotConfig(
        tenant_id=uuid.uuid4(),
        channel=cb_const.CHANNEL_WHATSAPP,
        tone=cb_const.TONE_FRIENDLY,
        goals=["support", "convert"],
        instructions="Mention the 14-day trial.",
        conversion={"cta_text": "Start trial", "cta_url": "https://example.com/trial"},
        fallback_message="Please contact support.",
    )
    text = chatbot_service.build_system_prompt_text(row)
    assert "WhatsApp" in text
    assert "approachable" in text.lower()
    assert "14-day trial" in text
    assert "Start trial" in text
    assert "Please contact support." in text


def test_validate_tone_rejects_unknown():
    with pytest.raises(ValueError, match="tone must be one of"):
        chatbot_service._validate_tone("sarcastic")


def test_validate_goals_dedupes():
    assert chatbot_service._validate_goals(["support", "SUPPORT", "convert"]) == [
        "support",
        "convert",
    ]


def test_chatbot_routes_registered():
    from app.main import app

    paths = set(app.openapi()["paths"])
    for p in (
        "/chatbot/whatsapp/config",
        "/chatbot/whatsapp/test",
    ):
        assert p in paths


def test_missing_chatbot_table_detection():
    from app.modules.chatbot.repository import _is_missing_chatbot_table

    class UndefinedTableError(Exception):
        pass

    class FakeOrig(UndefinedTableError):
        pass

    class FakeExc:
        orig = FakeOrig('relation "chatbot_configs" does not exist')

    assert _is_missing_chatbot_table(FakeExc())  # type: ignore[arg-type]
