"""Model Gateway data contracts.

Pure data — no provider libraries imported here — so every layer can depend on
these types without pulling in a specific SDK.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    finish_reason: str = "stop"


@dataclass
class StreamChunk:
    text: str


@dataclass
class ModelProfile:
    """A named model configuration callers request instead of a concrete model."""

    name: str
    provider: str
    model: str
    temperature: float | None = None
    max_tokens: int | None = None
    fallback: str | None = None
    timeout: float | None = None
    retries: int | None = None
