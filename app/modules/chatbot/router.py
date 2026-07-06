"""Chatbot configuration router — tenant-scoped WhatsApp behavior settings."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.modules.chatbot import schemas
from app.modules.chatbot import service as chatbot_service
from app.modules.chatbot.exceptions import ChatbotDisabledError, ChatbotVersionConflictError
from app.modules.conversation import service as chat_service
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.security.sanitize import InvalidInput, sanitize_identifier, sanitize_message
from app.platform.tenancy.context import TenantContext
from app.platform.tenancy.request_context import RequestContext

router = APIRouter(prefix="/chatbot", tags=["chatbot"])

_CHANNEL = schemas.DEFAULT_CHANNEL
_READ = require_permission(Permission.KB_READ)
_WRITE = require_permission(Permission.KB_WRITE)


def _tenant_id(ctx: TenantContext) -> uuid.UUID:
    tid = ctx.tenant_uuid()
    if tid is None:
        raise HTTPException(
            status_code=400,
            detail="Chatbot configuration requires an authenticated UUID tenant.",
        )
    return tid


@router.get("/whatsapp/config", response_model=schemas.ChatbotConfigOut)
async def get_whatsapp_config(
    ctx: TenantContext = Depends(_READ),
) -> schemas.ChatbotConfigOut:
    return await chatbot_service.get_config_out(_tenant_id(ctx), _CHANNEL)


@router.put("/whatsapp/config", response_model=schemas.ChatbotConfigOut)
async def put_whatsapp_config(
    payload: schemas.ChatbotConfigPut,
    ctx: TenantContext = Depends(_WRITE),
) -> schemas.ChatbotConfigOut:
    try:
        return await chatbot_service.replace_config(_tenant_id(ctx), _CHANNEL, payload)
    except ChatbotVersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/whatsapp/config", response_model=schemas.ChatbotConfigOut)
async def patch_whatsapp_config(
    payload: schemas.ChatbotConfigPatch,
    ctx: TenantContext = Depends(_WRITE),
) -> schemas.ChatbotConfigOut:
    try:
        return await chatbot_service.patch_config(_tenant_id(ctx), _CHANNEL, payload)
    except ChatbotVersionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/whatsapp/test", response_model=schemas.ChatbotTestResponse)
async def test_whatsapp_config(
    payload: schemas.ChatbotTestRequest,
    ctx: RequestContext = Depends(_WRITE),
) -> schemas.ChatbotTestResponse:
    """Sandbox reply using current config + KB; does not persist or send to WhatsApp."""
    try:
        message = sanitize_message(payload.message)
        user_number = sanitize_identifier(payload.user_number or "test-user", "user_number")
        company_id = sanitize_identifier(
            payload.company_id or ctx.tenant_id, "company_id"
        )
    except InvalidInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Ensure agent/channel headers are set for WhatsApp-scoped prompts + KB.
    if not ctx.agent:
        ctx.agent = _CHANNEL
    if not ctx.channel:
        ctx.channel = _CHANNEL

    try:
        await chatbot_service.ensure_chatbot_enabled(ctx, _CHANNEL)
    except ChatbotDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    config = await chatbot_service.get_config_row(_tenant_id(ctx), _CHANNEL)
    product = config.product if config else None

    result = await chat_service.handle(
        company_id=company_id,
        user_number=user_number,
        message=message,
        tenant_ctx=ctx,
        product=product,
        persist=False,
    )
    return schemas.ChatbotTestResponse(answer=result.answer, sources=result.sources)
