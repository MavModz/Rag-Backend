"""Lightweight query intent helpers for chat formatting."""
from __future__ import annotations

import re

_PROCEDURAL = re.compile(
    r"\b("
    r"how\s+(?:do|to|can|should)|"
    r"how\s+i\s+|"
    r"steps?\s+to|"
    r"walk\s*me\s+through|"
    r"guide\s+me|"
    r"show\s+me\s+how|"
    r"set\s+up|"
    r"create\s+a|"
    r"configure|"
    r"enrol|"
    r"enroll|"
    r"add\s+a\s+"
    r")\b",
    re.IGNORECASE,
)


def is_procedural_query(message: str) -> bool:
    """True when the user likely wants step-by-step instructions."""
    text = message.strip()
    if not text:
        return False
    return bool(_PROCEDURAL.search(text))
