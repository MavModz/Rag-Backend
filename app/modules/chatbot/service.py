"""Chatbot configuration business logic and prompt sync."""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.chatbot import constants as cb_const
from app.modules.chatbot import repository as repo
from app.modules.chatbot.exceptions import ChatbotDisabledError, ChatbotVersionConflictError
from app.modules.chatbot.models import ChatbotConfig
from app.modules.chatbot.schemas import (
    ChatbotConfigOut,
    ChatbotConfigPatch,
    ChatbotConfigPut,
    ConversionSettings,
)
from app.modules.conversation import prompts as conv_prompts
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
from app.modules.model_gateway.models import Configuration, PromptTemplate
from app.platform.db.postgres import get_sessionmaker
from app.platform.tenancy.constants import KNOWN_PRODUCTS, PRODUCT_CRM
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.request_context import RequestContext


def _default_fallback() -> str:
    return (
        "I do not have that information in my knowledge base. "
        "Would you like to speak with a human agent?"
    )


def _validate_tone(tone: str) -> str:
    slug = tone.strip().lower()
    if slug not in cb_const.KNOWN_TONES:
        raise ValueError(f"tone must be one of {sorted(cb_const.KNOWN_TONES)}")
    return slug


def _validate_goals(goals: list[str]) -> list[str]:
    out: list[str] = []
    for goal in goals:
        slug = goal.strip().lower()
        if slug not in cb_const.KNOWN_GOALS:
            raise ValueError(f"Unknown goal {goal!r}; allowed: {sorted(cb_const.KNOWN_GOALS)}")
        if slug not in out:
            out.append(slug)
    return out


def _validate_product(product: str) -> str:
    slug = product.strip().lower()
    if slug not in KNOWN_PRODUCTS:
        raise ValueError(f"product must be one of {sorted(KNOWN_PRODUCTS)}")
    return slug


def to_out(row: ChatbotConfig) -> ChatbotConfigOut:
    conversion = row.conversion or {}
    return ChatbotConfigOut(
        id=str(row.id),
        channel=row.channel,
        enabled=row.enabled,
        name=row.name,
        tone=row.tone,
        goals=list(row.goals or []),
        instructions=row.instructions or "",
        conversion=ConversionSettings(
            cta_text=conversion.get("cta_text"),
            cta_url=conversion.get("cta_url"),
            lead_capture_prompt=conversion.get("lead_capture_prompt"),
        ),
        greeting_message=row.greeting_message,
        fallback_message=row.fallback_message,
        handoff_keywords=list(row.handoff_keywords or []),
        kb_scope=row.kb_scope,
        product=row.product,
        model_profile=row.model_profile,
        version=row.version,
        updated_at=row.updated_at,
    )


def resolve_channel(tenant_ctx: TenantContext | None) -> str | None:
    """Return chatbot channel slug when the request is WhatsApp-scoped."""
    if not isinstance(tenant_ctx, RequestContext):
        return None
    if tenant_ctx.agent == cb_const.CHANNEL_WHATSAPP:
        return cb_const.CHANNEL_WHATSAPP
    return None


def build_system_prompt_text(row: ChatbotConfig, *, procedural: bool = False) -> str:
    """Compose the full system prompt from config + shared conversation rules."""
    parts = [
        conv_prompts.SYSTEM_PROMPT.strip(),
        "",
        "Channel: WhatsApp. Keep replies short and suitable for mobile chat.",
    ]
    tone_line = cb_const.TONE_INSTRUCTIONS.get(row.tone, "")
    if tone_line:
        parts.append(tone_line)
    for goal in row.goals or []:
        goal_line = cb_const.GOAL_INSTRUCTIONS.get(goal)
        if goal_line:
            parts.append(goal_line)
    if row.instructions and row.instructions.strip():
        parts.append(f"Tenant instructions:\n{row.instructions.strip()}")
    conversion = row.conversion or {}
    cta_bits: list[str] = []
    if conversion.get("cta_text"):
        cta_bits.append(f"CTA: {conversion['cta_text']}")
    if conversion.get("cta_url"):
        cta_bits.append(f"CTA URL: {conversion['cta_url']}")
    if conversion.get("lead_capture_prompt"):
        cta_bits.append(f"Lead capture: {conversion['lead_capture_prompt']}")
    if cta_bits:
        parts.append("Conversion guidance:\n" + "\n".join(cta_bits))
    if row.fallback_message and row.fallback_message.strip():
        parts.append(
            "When the knowledge base has no answer, say:\n"
            f"{row.fallback_message.strip()}"
        )
    addendum = (
        conv_prompts.PROCEDURAL_SYSTEM_ADDENDUM
        if procedural
        else conv_prompts.GENERAL_SYSTEM_ADDENDUM
    )
    parts.append(addendum.strip())
    # Hard platform safety rules always win over tenant tone/instructions.
    parts.append(conv_prompts.SAFETY_SYSTEM_ADDENDUM.strip())
    return "\n\n".join(p for p in parts if p)


async def get_or_create_config(
    session: AsyncSession, tenant_id: uuid.UUID, channel: str
) -> ChatbotConfig:
    row = await repo.get_by_tenant_channel(session, tenant_id, channel)
    if row is None:
        row = await repo.create_default(session, tenant_id, channel)
    return row


async def _serialize_after_commit(
    session: AsyncSession, row: ChatbotConfig
) -> ChatbotConfigOut:
    """Commit, refresh server defaults (e.g. updated_at), then build API output.

    Async SQLAlchemy cannot lazy-load expired attributes after the session
    closes; refresh while the session is still open.
    """
    await session.commit()
    await session.refresh(row)
    return to_out(row)


async def get_config_out(tenant_id: uuid.UUID, channel: str) -> ChatbotConfigOut:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await get_or_create_config(session, tenant_id, channel)
        return await _serialize_after_commit(session, row)


async def _sync_prompt_rows(session: AsyncSession, tenant_id: uuid.UUID, row: ChatbotConfig) -> None:
    """Mirror config into PromptTemplate + Configuration for runtime and auditing."""
    system_body = build_system_prompt_text(row, procedural=False)
    pt = (
        await session.execute(
            select(PromptTemplate).where(
                PromptTemplate.tenant_id == tenant_id,
                PromptTemplate.key == cb_const.PROMPT_KEY_SYSTEM,
            )
        )
    ).scalar_one_or_none()
    if pt is None:
        session.add(
            PromptTemplate(
                tenant_id=tenant_id,
                key=cb_const.PROMPT_KEY_SYSTEM,
                version=row.version,
                body=system_body,
            )
        )
    else:
        pt.body = system_body
        pt.version = row.version

    behavior = {
        "tone": row.tone,
        "goals": row.goals,
        "conversion": row.conversion,
        "greeting_message": row.greeting_message,
        "fallback_message": row.fallback_message,
        "handoff_keywords": row.handoff_keywords,
        "enabled": row.enabled,
    }
    cfg = (
        await session.execute(
            select(Configuration).where(
                Configuration.tenant_id == tenant_id,
                Configuration.key == cb_const.CONFIG_KEY_BEHAVIOR,
            )
        )
    ).scalar_one_or_none()
    if cfg is None:
        session.add(
            Configuration(
                tenant_id=tenant_id,
                key=cb_const.CONFIG_KEY_BEHAVIOR,
                value=behavior,
            )
        )
    else:
        cfg.value = behavior


def _apply_put(row: ChatbotConfig, payload: ChatbotConfigPut) -> None:
    row.enabled = payload.enabled
    row.name = payload.name
    row.tone = _validate_tone(payload.tone)
    row.goals = _validate_goals(payload.goals)
    row.instructions = payload.instructions or ""
    row.conversion = payload.conversion.model_dump()
    row.greeting_message = payload.greeting_message
    row.fallback_message = payload.fallback_message or _default_fallback()
    row.handoff_keywords = [k.strip().lower() for k in payload.handoff_keywords if k.strip()]
    row.kb_scope = payload.kb_scope or DEFAULT_KB_SCOPE
    row.product = _validate_product(payload.product)
    row.model_profile = payload.model_profile


def _apply_patch(row: ChatbotConfig, payload: ChatbotConfigPatch) -> None:
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.name is not None:
        row.name = payload.name
    if payload.tone is not None:
        row.tone = _validate_tone(payload.tone)
    if payload.goals is not None:
        row.goals = _validate_goals(payload.goals)
    if payload.instructions is not None:
        row.instructions = payload.instructions
    if payload.conversion is not None:
        row.conversion = payload.conversion.model_dump()
    if payload.greeting_message is not None:
        row.greeting_message = payload.greeting_message
    if payload.fallback_message is not None:
        row.fallback_message = payload.fallback_message
    if payload.handoff_keywords is not None:
        row.handoff_keywords = [k.strip().lower() for k in payload.handoff_keywords if k.strip()]
    if payload.kb_scope is not None:
        row.kb_scope = payload.kb_scope
    if payload.product is not None:
        row.product = _validate_product(payload.product)
    if payload.model_profile is not None:
        row.model_profile = payload.model_profile


def _check_version(row: ChatbotConfig, expected: int | None) -> None:
    if expected is None:
        return
    if row.version != expected:
        raise ChatbotVersionConflictError(expected, row.version)


async def replace_config(
    tenant_id: uuid.UUID, channel: str, payload: ChatbotConfigPut
) -> ChatbotConfigOut:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await get_or_create_config(session, tenant_id, channel)
        _check_version(row, payload.version)
        _apply_put(row, payload)
        row.version += 1
        await _sync_prompt_rows(session, tenant_id, row)
        return await _serialize_after_commit(session, row)


async def patch_config(
    tenant_id: uuid.UUID, channel: str, payload: ChatbotConfigPatch
) -> ChatbotConfigOut:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await get_or_create_config(session, tenant_id, channel)
        _check_version(row, payload.version)
        _apply_patch(row, payload)
        row.version += 1
        await _sync_prompt_rows(session, tenant_id, row)
        return await _serialize_after_commit(session, row)


async def ensure_chatbot_enabled(tenant_ctx: TenantContext, channel: str) -> None:
    """Raise if a config row exists and is disabled (WhatsApp routing gate)."""
    tenant_id = tenant_ctx.tenant_uuid()
    if tenant_id is None:
        return
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await repo.get_by_tenant_channel(session, tenant_id, channel)
        if row is not None and not row.enabled:
            raise ChatbotDisabledError(f"Chatbot disabled for channel {channel!r}")


async def resolve_system_prompt(
    tenant_ctx: TenantContext | None,
    *,
    channel: str | None,
    procedural: bool = False,
) -> str | None:
    """Return tenant-specific system prompt, or None to use code defaults."""
    if not channel or tenant_ctx is None:
        return None
    tenant_id = tenant_ctx.tenant_uuid()
    if tenant_id is None:
        return None
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await repo.get_by_tenant_channel(session, tenant_id, channel)
        if row is None:
            return None
        return build_system_prompt_text(row, procedural=procedural)


async def get_config_row(
    tenant_id: uuid.UUID, channel: str
) -> ChatbotConfig | None:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        row = await repo.get_by_tenant_channel(session, tenant_id, channel)
        if row is None:
            return None
        await session.refresh(row)
        session.expunge(row)
        return row
