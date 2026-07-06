"""Chatbot configuration request/response models."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.chatbot.constants import CHANNEL_WHATSAPP, TONE_FRIENDLY
from app.modules.knowledge.constants import DEFAULT_KB_SCOPE
from app.platform.tenancy.constants import PRODUCT_CRM


class ConversionSettings(BaseModel):
    cta_text: str | None = None
    cta_url: str | None = None
    lead_capture_prompt: str | None = None


class ChatbotConfigOut(BaseModel):
    id: str
    channel: str
    enabled: bool
    name: str
    tone: str
    goals: list[str] = Field(default_factory=list)
    instructions: str = ""
    conversion: ConversionSettings = Field(default_factory=ConversionSettings)
    greeting_message: str | None = None
    fallback_message: str | None = None
    handoff_keywords: list[str] = Field(default_factory=list)
    kb_scope: str = DEFAULT_KB_SCOPE
    product: str = PRODUCT_CRM
    model_profile: str | None = None
    version: int = 1
    updated_at: datetime | None = None


class ChatbotConfigPut(BaseModel):
    """Full replace; requires ``version`` for optimistic locking."""

    version: int
    enabled: bool = True
    name: str = Field(default="WhatsApp Bot", max_length=128)
    tone: str = TONE_FRIENDLY
    goals: list[str] = Field(default_factory=list)
    instructions: str = ""
    conversion: ConversionSettings = Field(default_factory=ConversionSettings)
    greeting_message: str | None = None
    fallback_message: str | None = None
    handoff_keywords: list[str] = Field(default_factory=list)
    kb_scope: str = DEFAULT_KB_SCOPE
    product: str = PRODUCT_CRM
    model_profile: str | None = None


class ChatbotConfigPatch(BaseModel):
    """Partial update; include ``version`` when provided for optimistic locking."""

    version: int | None = None
    enabled: bool | None = None
    name: str | None = Field(default=None, max_length=128)
    tone: str | None = None
    goals: list[str] | None = None
    instructions: str | None = None
    conversion: ConversionSettings | None = None
    greeting_message: str | None = None
    fallback_message: str | None = None
    handoff_keywords: list[str] | None = None
    kb_scope: str | None = None
    product: str | None = None
    model_profile: str | None = None


class SimulatedTurn(BaseModel):
    role: str
    content: str


class ChatbotTestRequest(BaseModel):
    message: str = Field(..., min_length=1)
    simulate_history: list[SimulatedTurn] = Field(default_factory=list)
    company_id: str | None = None
    user_number: str | None = "test-user"


class ChatbotTestResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)


DEFAULT_CHANNEL = CHANNEL_WHATSAPP
