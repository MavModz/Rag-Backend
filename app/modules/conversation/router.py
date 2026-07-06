"""Conversation router: request/response only. All logic lives in the service.

Phase 6 adds auth + tenant-context dependencies and rate limiting here; the
route bodies stay logic-free per .claude/rules.md.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.config import settings
from app.modules.chatbot.exceptions import ChatbotDisabledError
from app.modules.conversation import service as chat_service
from app.modules.conversation.schemas import ChatRequest, ChatResponse
from app.modules.knowledge.constants import DEFAULT_CHAT_PRODUCT
from app.platform.tenancy.constants import KNOWN_PRODUCTS
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.ratelimit.limiter import limiter
from app.platform.security.sanitize import (
    InvalidInput,
    sanitize_identifier,
    sanitize_message,
)
from app.platform.tenancy.request_context import RequestContext

router = APIRouter(tags=["conversation"])


def _resolve_product(payload: ChatRequest, ctx: RequestContext) -> str:
    raw = (payload.product or ctx.product or settings.default_chat_product or DEFAULT_CHAT_PRODUCT)
    slug = raw.strip().lower()
    return slug if slug in KNOWN_PRODUCTS else DEFAULT_CHAT_PRODUCT


def _resolve(payload: ChatRequest, ctx: RequestContext) -> tuple[str, str, str, str]:
    """Resolve + sanitize inputs. Defaults come from ``RequestContext`` (tenant,
    session, product user) when body fields are omitted."""
    try:
        company_id = sanitize_identifier(payload.company_id or ctx.tenant_id, "company_id")
        if payload.session_id:
            ctx.session_id = payload.session_id
        user_number = sanitize_identifier(
            payload.user_number
            or ctx.conversation_key()
            or ctx.external_user_id
            or ctx.user_id
            or "web",
            "user_number",
        )
        message = sanitize_message(payload.message)
    except InvalidInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return company_id, user_number, message, _resolve_product(payload, ctx)


@router.post("/chat", response_model=ChatResponse)
@limiter.limit(settings.rate_limit_chat)
async def chat(
    request: Request,
    payload: ChatRequest,
    ctx: RequestContext = Depends(require_permission(Permission.CHAT_WRITE)),
) -> ChatResponse:
    company_id, user_number, message, product = _resolve(payload, ctx)
    try:
        result = await chat_service.handle(
            company_id=company_id,
            user_number=user_number,
            message=message,
            tenant_ctx=ctx,
            product=product,
        )
    except ChatbotDisabledError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ChatResponse(answer=result.answer, sources=result.sources)


@router.post("/chat/stream")
@limiter.limit(settings.rate_limit_chat)
async def chat_stream(
    request: Request,
    payload: ChatRequest,
    ctx: RequestContext = Depends(require_permission(Permission.CHAT_WRITE)),
) -> StreamingResponse:
    """Stream the answer as Server-Sent Events (token + done events)."""
    company_id, user_number, message, product = _resolve(payload, ctx)

    async def event_source():
        try:
            async for event in chat_service.stream(
                company_id=company_id,
                user_number=user_number,
                message=message,
                tenant_ctx=ctx,
                product=product,
            ):
                yield f"data: {json.dumps(event)}\n\n"
        except ChatbotDisabledError as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc), 'status': 503})}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface errors to the client
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
