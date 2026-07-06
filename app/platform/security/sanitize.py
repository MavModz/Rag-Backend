"""Input sanitization and basic prompt-injection guards.

Rules (.claude/rules.md): never trust user input; sanitize inputs; block
injection attempts. This is a pragmatic first line of defense, not a complete
solution — defense in depth (the system prompt also constrains the model).
"""
from __future__ import annotations

import re

MAX_MESSAGE_LEN = 4000

# Strip ASCII control chars except tab/newline/carriage-return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Heuristic phrases commonly used in prompt-injection attempts.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(the\s+)?(above|previous)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+(instructions|prompt)", re.IGNORECASE),
]


class InvalidInput(ValueError):
    pass


def sanitize_message(text: str) -> str:
    """Validate and clean a user-supplied chat message.

    Raises InvalidInput for empty/oversized input. Returns cleaned text with
    control characters and injection phrases neutralized.
    """
    if not isinstance(text, str):
        raise InvalidInput("message must be a string")
    cleaned = _CONTROL_CHARS.sub("", text).strip()
    if not cleaned:
        raise InvalidInput("message must not be empty")
    if len(cleaned) > MAX_MESSAGE_LEN:
        raise InvalidInput(f"message exceeds {MAX_MESSAGE_LEN} characters")
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[filtered]", cleaned)
    return cleaned


def sanitize_identifier(value: str, field: str) -> str:
    """Lightweight validation for ids/phone numbers used in DB queries."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f"{field} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > 128:
        raise InvalidInput(f"{field} is too long")
    return cleaned
