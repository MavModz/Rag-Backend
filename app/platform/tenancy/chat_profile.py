"""Chat routing profile: agent -> retrieval layer + prompt source."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config import settings
from app.modules.chatbot import constants as cb_const
from app.modules.chatbot import service as chatbot_service
from app.modules.knowledge.constants import DEFAULT_CHAT_PRODUCT, DEFAULT_KB_SCOPE
from app.platform.tenancy.constants import (
    AGENT_PLATFORM_HELP,
    AGENT_PROMPT_SOURCE,
    AGENT_RETRIEVAL_PROFILE,
    AGENT_WHATSAPP,
    KNOWN_PRODUCTS,
    PRODUCT_LMS,
    RETRIEVAL_PLATFORM_AND_TENANT,
    RETRIEVAL_PLATFORM_ONLY,
    RETRIEVAL_TENANT_ONLY,
)
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.request_context import RequestContext, agent_to_kb_scope

RetrievalProfile = Literal["platform_only", "tenant_only", "platform_and_tenant"]
PromptSource = Literal["platform_help", "default", "chatbot"]


@dataclass(frozen=True)
class ChatProfile:
    """Resolved chat behavior for one request."""

    agent: str | None
    kb_scope: str
    retrieval: RetrievalProfile
    prompt_source: PromptSource
    channel: str | None
    chatbot_channel: str | None
    product: str


def _resolve_product(
    tenant_ctx: TenantContext | None, product_override: str | None
) -> str:
    if product_override:
        slug = product_override.strip().lower()
        if slug in KNOWN_PRODUCTS:
            return slug
    if isinstance(tenant_ctx, RequestContext) and tenant_ctx.product:
        return tenant_ctx.product
    default = settings.default_chat_product or DEFAULT_CHAT_PRODUCT
    return default if default in KNOWN_PRODUCTS else PRODUCT_LMS


async def resolve_chat_profile(
    tenant_ctx: TenantContext | None,
    *,
    product: str | None = None,
) -> ChatProfile:
    """Map request agent/headers to retrieval + prompt rules."""
    agent: str | None = None
    channel: str | None = None
    if isinstance(tenant_ctx, RequestContext):
        agent = tenant_ctx.agent
        channel = tenant_ctx.channel

    chat_product = _resolve_product(tenant_ctx, product)
    kb_scope = agent_to_kb_scope(agent) if agent else DEFAULT_KB_SCOPE
    retrieval: RetrievalProfile = AGENT_RETRIEVAL_PROFILE.get(
        agent, RETRIEVAL_PLATFORM_AND_TENANT
    )
    prompt_source: PromptSource = AGENT_PROMPT_SOURCE.get(agent, "default")
    chatbot_channel: str | None = None

    if agent == AGENT_WHATSAPP:
        chatbot_channel = cb_const.CHANNEL_WHATSAPP
        tenant_id = tenant_ctx.tenant_uuid() if tenant_ctx else None
        if tenant_id is not None:
            row = await chatbot_service.get_config_row(tenant_id, cb_const.CHANNEL_WHATSAPP)
            if row is not None:
                kb_scope = row.kb_scope or DEFAULT_KB_SCOPE
                chat_product = row.product or chat_product
    elif agent == AGENT_PLATFORM_HELP:
        kb_scope = DEFAULT_KB_SCOPE
        retrieval = RETRIEVAL_PLATFORM_ONLY
        prompt_source = "platform_help"

    return ChatProfile(
        agent=agent,
        kb_scope=kb_scope,
        retrieval=retrieval,
        prompt_source=prompt_source,
        channel=channel,
        chatbot_channel=chatbot_channel,
        product=chat_product,
    )
