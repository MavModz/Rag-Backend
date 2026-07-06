"""Conversation agent: orchestration only.

Given already-built context blocks, assembles the prompt and calls the LLM
through the Model Gateway — it requests the ``conversation.default`` profile and
never names a provider, so routing/retry/fallback/usage all happen in the
gateway. No retrieval or DB access happens here (that belongs to the
Knowledge/connector layers).
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from app.modules.chatbot import service as chatbot_service
from app.modules.conversation import prompts
from app.platform.gateway.gateway import get_gateway
from app.platform.gateway.types import Message
from app.platform.tenancy.chat_profile import PromptSource
from app.platform.tenancy.context import TenantContext

_PROFILE = "conversation.default"


async def _system_prompt(
    tenant_ctx: TenantContext | None,
    *,
    prompt_source: PromptSource,
    chatbot_channel: str | None,
    procedural: bool,
) -> str:
    if prompt_source == "platform_help":
        return prompts.build_platform_help_system_prompt(procedural=procedural)
    if prompt_source == "chatbot" and chatbot_channel:
        custom = await chatbot_service.resolve_system_prompt(
            tenant_ctx, channel=chatbot_channel, procedural=procedural
        )
        if custom:
            return custom
    return prompts.build_system_prompt(procedural=procedural)


async def _messages(
    kb_context: str,
    history: str,
    question: str,
    memory_context: str = "",
    *,
    tenant_ctx: TenantContext | None = None,
    prompt_source: PromptSource = "default",
    chatbot_channel: str | None = None,
    procedural: bool = False,
) -> list[Message]:
    user_prompt = prompts.build_user_prompt(
        kb_context=kb_context,
        history=history,
        question=question,
        memory_context=memory_context,
        procedural=procedural,
    )
    system = await _system_prompt(
        tenant_ctx,
        prompt_source=prompt_source,
        chatbot_channel=chatbot_channel,
        procedural=procedural,
    )
    return [
        Message("system", system),
        Message("user", user_prompt),
    ]


async def generate_answer(
    kb_context: str,
    history: str,
    question: str,
    tenant_ctx: TenantContext | None = None,
    memory_context: str = "",
    *,
    prompt_source: PromptSource = "default",
    chatbot_channel: str | None = None,
    procedural: bool = False,
) -> str:
    result = await get_gateway().generate(
        _PROFILE,
        await _messages(
            kb_context,
            history,
            question,
            memory_context,
            tenant_ctx=tenant_ctx,
            prompt_source=prompt_source,
            chatbot_channel=chatbot_channel,
            procedural=procedural,
        ),
        tenant_ctx=tenant_ctx,
    )
    return result.text


async def stream_answer(
    kb_context: str,
    history: str,
    question: str,
    tenant_ctx: TenantContext | None = None,
    memory_context: str = "",
    *,
    prompt_source: PromptSource = "default",
    chatbot_channel: str | None = None,
    procedural: bool = False,
) -> AsyncIterator[str]:
    message_list = await _messages(
        kb_context,
        history,
        question,
        memory_context,
        tenant_ctx=tenant_ctx,
        prompt_source=prompt_source,
        chatbot_channel=chatbot_channel,
        procedural=procedural,
    )
    async for chunk in get_gateway().stream(
        _PROFILE,
        message_list,
        tenant_ctx=tenant_ctx,
    ):
        yield chunk.text
