"""Memory router: promote verified Q&A into long-term tenant memory."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.modules.memory import service as memory_service
from app.modules.memory.schemas import MemoryFeedbackRequest, MemoryFeedbackResponse
from app.platform.auth.dependencies import require_permission
from app.platform.auth.rbac import Permission
from app.platform.security.sanitize import InvalidInput, sanitize_identifier, sanitize_message
from app.platform.tenancy.context import TenantContext

router = APIRouter(prefix="/memory", tags=["memory"])


@router.post("/feedback", response_model=MemoryFeedbackResponse)
async def feedback(
    payload: MemoryFeedbackRequest,
    ctx: TenantContext = Depends(require_permission(Permission.CHAT_WRITE)),
) -> MemoryFeedbackResponse:
    """Store a verified Q&A pair for cross-user retrieval on similar questions."""
    try:
        question = sanitize_message(payload.question)
        answer = sanitize_message(payload.answer)
        user_number = (
            sanitize_identifier(payload.user_number, "user_number")
            if payload.user_number
            else None
        )
    except InvalidInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await memory_service.store_verified_qa(
        ctx, question, answer, external_user_id=user_number
    )
    return MemoryFeedbackResponse()
