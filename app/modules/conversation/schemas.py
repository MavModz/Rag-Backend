"""Request/response models for the Conversation Service chat endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.modules.knowledge.constants import DEFAULT_CHAT_PRODUCT


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's current message.")
    product: str | None = Field(
        default=None,
        description="lms or crm — selects parent-company help docs to retrieve.",
    )
    company_id: str | None = Field(default=None, description="External company/tenant id.")
    user_number: str | None = Field(default=None, description="External end-user id.")
    session_id: str | None = Field(default=None, description="Optional client session id.")


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
