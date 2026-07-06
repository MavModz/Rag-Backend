"""Chat routing profile unit tests."""
from __future__ import annotations

import asyncio
import uuid

from app.modules.chatbot import constants as cb_const
from app.platform.tenancy.constants import (
    AGENT_PLATFORM_HELP,
    AGENT_SUPPORT,
    AGENT_WHATSAPP,
    RETRIEVAL_PLATFORM_AND_TENANT,
    RETRIEVAL_PLATFORM_ONLY,
    RETRIEVAL_TENANT_ONLY,
)
from app.platform.tenancy.chat_profile import resolve_chat_profile
from app.platform.tenancy.request_context import RequestContext


def test_platform_help_profile():
    ctx = RequestContext(
        tenant_id=str(uuid.uuid4()),
        scopes=["chat:write"],
        agent=AGENT_PLATFORM_HELP,
        product="lms",
    )
    profile = asyncio.run(resolve_chat_profile(ctx))
    assert profile.retrieval == RETRIEVAL_PLATFORM_ONLY
    assert profile.prompt_source == "platform_help"
    assert profile.chatbot_channel is None
    assert profile.kb_scope == "support"
    assert profile.product == "lms"


def test_whatsapp_profile_defaults_without_config(monkeypatch):
    ctx = RequestContext(
        tenant_id=str(uuid.uuid4()),
        scopes=["chat:write"],
        agent=AGENT_WHATSAPP,
    )

    async def _no_config(_tid, _channel):
        return None

    monkeypatch.setattr(
        "app.platform.tenancy.chat_profile.chatbot_service.get_config_row",
        _no_config,
    )
    profile = asyncio.run(resolve_chat_profile(ctx))
    assert profile.retrieval == RETRIEVAL_TENANT_ONLY
    assert profile.prompt_source == "chatbot"
    assert profile.chatbot_channel == cb_const.CHANNEL_WHATSAPP


def test_support_profile_hybrid_retrieval():
    ctx = RequestContext(
        tenant_id=str(uuid.uuid4()),
        scopes=["chat:write"],
        agent=AGENT_SUPPORT,
        product="crm",
    )
    profile = asyncio.run(resolve_chat_profile(ctx))
    assert profile.retrieval == RETRIEVAL_PLATFORM_AND_TENANT
    assert profile.prompt_source == "default"
    assert profile.chatbot_channel is None


def test_whatsapp_profile_uses_config_kb_scope(monkeypatch):
    tenant_id = uuid.uuid4()
    ctx = RequestContext(
        tenant_id=str(tenant_id),
        scopes=["chat:write"],
        agent=AGENT_WHATSAPP,
    )

    class _Row:
        kb_scope = "quiz"
        product = "crm"

    async def _fake_row(_tid, _channel):
        return _Row()

    monkeypatch.setattr(
        "app.platform.tenancy.chat_profile.chatbot_service.get_config_row",
        _fake_row,
    )
    profile = asyncio.run(resolve_chat_profile(ctx))
    assert profile.kb_scope == "quiz"
    assert profile.product == "crm"
