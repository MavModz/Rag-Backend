"""Input sanitization and basic prompt-injection guards.

Rules (.claude/rules.md): never trust user input; sanitize inputs; block
injection attempts. This is a pragmatic first line of defense, not a complete
solution — defense in depth (system prompt + output policy + memory filters).
"""
from __future__ import annotations

import re
import unicodedata

MAX_MESSAGE_LEN = 4000

# Strip ASCII control chars except tab/newline/carriage-return.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Zero-width / bidi overrides often used to hide jailbreak phrasing.
_INVISIBLE_CHARS = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]"
)

# Heuristic phrases commonly used in prompt-injection / instruction-override attempts.
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|all)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(the\s+)?(above|previous|prior|system)", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(your\s+)?(previous|prior|system)\s+instructions?", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
    re.compile(
        r"act\s+as\s+(if\s+you\s+(are|were)\s+|though\s+you\s+|a\s+)?"
        r"(system|admin|root|developer|jailbroken|unrestricted|dan)\b",
        re.IGNORECASE,
    ),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(a\s+)?(system|admin|unrestricted)", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"reveal\s+your\s+(instructions|prompt|system)", re.IGNORECASE),
    re.compile(r"show\s+(me\s+)?(your\s+)?(hidden\s+)?(system\s+)?prompt", re.IGNORECASE),
    re.compile(r"override\s+(the\s+)?(system|policy|rules?|instructions?)", re.IGNORECASE),
    re.compile(r"from\s+now\s+on\b", re.IGNORECASE),
    re.compile(r"new\s+(system\s+)?instructions?\s*:", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(the\s+)?(knowledge|kb|documentation|policy)", re.IGNORECASE),
    re.compile(r"always\s+(approve|grant|give|issue)\s+(a\s+|full\s+)?(refund|credit)", re.IGNORECASE),
    re.compile(r"refund\s+(all|every)\s+(users?|customers?|students?)", re.IGNORECASE),
    re.compile(r"tell\s+(all\s+)?(users?|customers?)\s+that", re.IGNORECASE),
    re.compile(r"your\s+new\s+policy\s+is", re.IGNORECASE),
    re.compile(r"update\s+(the\s+)?(refund|credit|pricing)\s+policy\s+to", re.IGNORECASE),
]

# Fake prompt-section / role markers that try to hijack template boundaries.
_DELIMITER_PATTERNS = [
    re.compile(r"(?im)^\s*(system|assistant)\s*:\s*"),
    re.compile(r"(?i)\[?\s*SYSTEM\s*\]?\s*:"),
    re.compile(r"(?i)<\|?(system|im_start|im_end)\|?>"),
    re.compile(r"(?i)knowledge\s+base\s+context\s*:"),
    re.compile(r"(?i)learnings\s+from\s+past\s+conversations\s*:"),
    re.compile(r"(?i)previous\s+conversation\s*:"),
    re.compile(r"(?i)current\s+user\s+message\s*:"),
    re.compile(r"(?i)tenant\s+instructions\s*:"),
]


class InvalidInput(ValueError):
    pass


def _normalize_unicode(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return _INVISIBLE_CHARS.sub("", text)


def sanitize_message(text: str) -> str:
    """Validate and clean a user-supplied chat message.

    Raises InvalidInput for empty/oversized input. Returns cleaned text with
    control characters and injection phrases neutralized.
    """
    if not isinstance(text, str):
        raise InvalidInput("message must be a string")
    cleaned = _CONTROL_CHARS.sub("", text)
    cleaned = _normalize_unicode(cleaned).strip()
    if not cleaned:
        raise InvalidInput("message must not be empty")
    if len(cleaned) > MAX_MESSAGE_LEN:
        raise InvalidInput(f"message exceeds {MAX_MESSAGE_LEN} characters")
    for pattern in _INJECTION_PATTERNS:
        cleaned = pattern.sub("[filtered]", cleaned)
    for pattern in _DELIMITER_PATTERNS:
        cleaned = pattern.sub("[filtered] ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if not cleaned or cleaned == "[filtered]":
        raise InvalidInput("message rejected: instruction override attempt")
    return cleaned


def sanitize_history_role(role: str) -> str:
    """Validate a pushed history turn role."""
    if not isinstance(role, str) or not role.strip():
        raise InvalidInput("history role must be user or assistant")
    normalized = role.strip().lower()
    if normalized not in ("user", "assistant"):
        raise InvalidInput("history role must be user or assistant")
    return normalized


def sanitize_history_turns(
    turns: list,
    *,
    max_turns: int,
) -> list[tuple[str, str]]:
    """Validate and clean pushed conversation history from a trusted BFF.

    Returns a list of (role, content) tuples in chronological order. If more
    than ``max_turns`` are supplied, keeps the most recent turns.
    """
    if max_turns < 1:
        raise InvalidInput("max_turns must be at least 1")
    cleaned: list[tuple[str, str]] = []
    for turn in turns:
        role = sanitize_history_role(getattr(turn, "role", ""))
        content = sanitize_message(getattr(turn, "content", ""))
        cleaned.append((role, content))
    if len(cleaned) > max_turns:
        cleaned = cleaned[-max_turns:]
    return cleaned


def sanitize_identifier(value: str, field: str) -> str:
    """Lightweight validation for ids/phone numbers used in DB queries."""
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f"{field} must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > 128:
        raise InvalidInput(f"{field} is too long")
    return cleaned
