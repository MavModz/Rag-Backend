"""Memory API schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MemoryFeedbackRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    answer: str = Field(..., min_length=1, max_length=16000)
    user_number: str | None = Field(None, max_length=255)


class MemoryFeedbackResponse(BaseModel):
    status: str = "stored"
